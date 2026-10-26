"""RehkopfPilot pass hints: suggest passing when a slower car has held the van back for a while on a divided road.

A hint is advice only: it never steers, signals or changes speed, and it says nothing about what is beside or behind the
van. This Odyssey's blind-spot sensors aren't visible to openpilot, and the driving model only sees cars in our own lane, so
the driver always checks mirrors and the lane ahead.

A hint needs all of:
  - a divided road: the offline map says this is one carriageway (OSM oneway), so the lane beside us goes our way and is
    never oncoming traffic; ramps don't count
  - a lane to move into: the road camera reads the line on that side as dashed white for most of the last few seconds,
    with no yellow (lane_paint.LineVote). Yellow is the median edge, solid white an edge or a turn bay
  - a slower car ahead that has held the van back for HELD_FOR seconds, slow enough that passing it is worth it: at least
    MIN_GAIN seconds saved over the next GAIN_HORIZON (or up to the next navigation turn), and with a known speed limit, at
    least SLOWER_THAN_LIMIT under it (when all traffic is slower than the driver likes, the left lane is no faster)
  - a calm moment: 40+ mph, straight road, no blinker or lane change, no turn coming up
And it backs off: once per car, never within MIN_INTERVAL of the last one, and only the pill (no chime) after
IGNORED_QUIET hints in a row went unused. Passing on the right (a slow car camping in the left lane) is opt-in.
"""
from collections import deque
from dataclasses import dataclass

from openpilot.common.constants import CV

MIN_SPEED = 40 * CV.MPH_TO_MS
MAX_SPEED = 90 * CV.MPH_TO_MS
ROAD_KINDS = ('highway', 'major_road')  # motorway, trunk, primary, secondary, tertiary
LEAD_PROB = 0.7
FOLLOW_GAP = 3.5  # s: closer than this the car ahead is what sets our speed
HELD_FOR = 10.0  # s behind the slow car before suggesting
GAIN_HORIZON = 3200.0  # m (2 miles)
MIN_GAIN = 15.0  # s saved over the horizon: ~9 mph slower at 70 mph, ~5.5 mph at 40 mph
NAV_CLEARANCE = 1600.0  # m: no hint when the next navigation turn or exit is closer than this (1 mile)
OVER_LIMIT = 7 * CV.MPH_TO_MS  # the speed we'd pass up to is capped at the speed limit plus this
SLOWER_THAN_LIMIT = 5 * CV.MPH_TO_MS  # with a known limit, a car ahead has to be this far under it to be slow
SECOND_CAR = 150.0  # m: a second slow car within this of the first gets counted
MAX_LAT_ACCEL = 1.0  # m/s^2 of curve: no hint in a curve
FREE_FLOW_WINDOW = 120.0  # s of history for the speed the driver chooses on their own
FREE_FLOW_MIN = 30.0  # s of it needed when there's no set speed
SHOW_FOR = 10.0  # s a hint stays up
ACCEPT_WITHIN = 15.0  # s: a lane change (or blinker) that way this soon after a hint used it
MIN_INTERVAL = 90.0  # s between hints
IGNORED_QUIET = 3  # unused hints in a row before going quiet (pill only)
NEW_LEAD_JUMP = 15.0  # m: a jump in distance larger than this is a different car ahead
BLINKER_MOVE_SPEED = 25 * CV.MPH_TO_MS  # a blinker above this counts as a lane move (manual changes have no lane-change state)

LANE_CHANGE_STARTING = 2
NONE, LEFT, RIGHT = 0, 1, 2
ELIGIBLE = ('none', 'already_hinted', 'too_soon')  # held back by the car ahead, even if a hint can't show right now


@dataclass
class PassInputs:
  t: float  # s, monotonic
  v_ego: float  # m/s
  set_speed: float | None  # m/s the driver set (openpilot or stock cruise), None when not cruising
  speed_limit: float | None  # m/s, None when unknown
  lead: bool
  lead_prob: float
  lead_dist: float  # m
  lead_speed: float  # m/s
  lead2: bool  # a second car further ahead in our lane
  lead2_dist: float  # m
  lead2_speed: float  # m/s
  left_line: str  # lane_paint.LineVote kind of the line on our left
  right_line: str
  curvature: float  # 1/m
  lane_change_state: int
  lane_change_dir: int
  left_blinker: bool
  right_blinker: bool
  oneway_road: bool  # matched to one carriageway of a divided road
  road_kind: str
  ramp: bool
  nav_distance: float | None  # m to the next navigation maneuver, None without a route


@dataclass
class PassAdvice:
  show: bool = False  # the pill is up
  direction: int = NONE  # LEFT or RIGHT while showing
  cars: int = 0  # slow cars ahead the hint is about (1 or 2)
  chime: bool = False  # True on the frame a new hint starts and it should chime
  count: int = 0  # hints shown this drive
  accepted: int = 0  # of them, followed by a lane change that way
  quiet: bool = False  # no chimes after repeated unused hints
  blocker: str = 'none'  # first unmet condition, for logs and tuning


class PassAdvisor:
  def __init__(self, allow_right: bool = False):
    self.allow_right = allow_right
    self.free_flow: deque[tuple[float, float]] = deque()
    self.held_since: float | None = None
    self.lead_dist_prev: float | None = None
    self.lead_hinted = False
    self.hint_start: float | None = None
    self.hint_dir = NONE
    self.hint_used = True
    self.last_hint = -1e9
    self.last_move = {LEFT: -1e9, RIGHT: -1e9}
    self.lc_prev = 0
    self.blinkers_prev = (False, False)
    self.ignored = 0
    self.advice = PassAdvice()

  def _desired_speed(self, i: PassInputs) -> float | None:
    """The speed the driver wants: their set speed, or the median of their own free-flowing speed lately."""
    if i.set_speed is not None:
      desired = i.set_speed
    else:
      if len(self.free_flow) < 2 or self.free_flow[-1][0] - self.free_flow[0][0] < FREE_FLOW_MIN:
        return None
      desired = sorted(v for _, v in self.free_flow)[len(self.free_flow) // 2]
    if i.speed_limit is not None and i.speed_limit > 0:
      desired = min(desired, i.speed_limit + OVER_LIMIT)
    return desired

  def _track(self, i: PassInputs) -> bool:
    """Bookkeeping every frame. Returns whether the car ahead is what sets our speed right now."""
    if i.lane_change_state == LANE_CHANGE_STARTING and self.lc_prev != LANE_CHANGE_STARTING and i.lane_change_dir in (LEFT, RIGHT):
      self.last_move[i.lane_change_dir] = i.t
    self.lc_prev = i.lane_change_state
    if i.v_ego > BLINKER_MOVE_SPEED:
      if i.left_blinker and not self.blinkers_prev[0]:
        self.last_move[LEFT] = i.t
      if i.right_blinker and not self.blinkers_prev[1]:
        self.last_move[RIGHT] = i.t
    self.blinkers_prev = (i.left_blinker, i.right_blinker)

    following = i.lead and i.lead_prob >= LEAD_PROB and i.v_ego > 1.0 and i.lead_dist / i.v_ego < FOLLOW_GAP
    if not following and i.v_ego > 5.0:
      self.free_flow.append((i.t, i.v_ego))
    while self.free_flow and i.t - self.free_flow[0][0] > FREE_FLOW_WINDOW:
      self.free_flow.popleft()

    if not following or self.lead_dist_prev is None or abs(i.lead_dist - self.lead_dist_prev) > NEW_LEAD_JUMP:
      self.lead_hinted = False  # a different car ahead (or none)
    self.lead_dist_prev = i.lead_dist if following else None
    return following

  def _side(self, i: PassInputs) -> int:
    """Which way a pass could go: left over a dashed white line, else right when allowed and the van is in the left lane."""
    if i.left_line == 'dashed_white':
      return LEFT
    if self.allow_right and i.right_line == 'dashed_white' and i.left_line in ('yellow', 'solid_white'):
      return RIGHT
    return NONE

  def _blocker(self, i: PassInputs, following: bool) -> str:
    """The first condition that rules out a hint now, or 'none'."""
    if not (MIN_SPEED <= i.v_ego <= MAX_SPEED):
      return 'speed'
    if not i.oneway_road or i.ramp or i.road_kind not in ROAD_KINDS:
      return 'road'
    if self._side(i) == NONE:
      return 'line'
    if i.v_ego ** 2 * abs(i.curvature) > MAX_LAT_ACCEL:
      return 'curve'
    if i.left_blinker or i.right_blinker or i.lane_change_state != 0:
      return 'signal'
    if i.nav_distance is not None and i.nav_distance < NAV_CLEARANCE:
      return 'turn'
    if not following:
      return 'no_lead'
    if i.speed_limit is not None and i.speed_limit > 0 and i.lead_speed > i.speed_limit - SLOWER_THAN_LIMIT:
      return 'not_slow'
    desired = self._desired_speed(i)
    if desired is None:
      return 'no_desired'
    horizon = GAIN_HORIZON if i.nav_distance is None else min(GAIN_HORIZON, i.nav_distance - NAV_CLEARANCE)
    gain = horizon * (1.0 / max(i.lead_speed, 1.0) - 1.0 / desired) if i.lead_speed < desired else 0.0
    if gain < MIN_GAIN:
      return 'not_worth'
    if self.lead_hinted:
      return 'already_hinted'
    if i.t - self.last_hint < MIN_INTERVAL:
      return 'too_soon'
    return 'none'

  def update(self, i: PassInputs) -> PassAdvice:
    following = self._track(i)
    blocker = self._blocker(i, following)
    a = self.advice
    a.chime = False

    if not self.hint_used and self.hint_dir != NONE and self.last_hint <= self.last_move[self.hint_dir] <= self.last_hint + ACCEPT_WITHIN:
      self.hint_used = True
      a.accepted += 1
      self.ignored = 0

    eligible = blocker in ELIGIBLE
    self.held_since = (i.t if self.held_since is None else self.held_since) if eligible else None

    if self.hint_start is not None and (self.hint_used or not eligible or i.t - self.hint_start > SHOW_FOR):
      self.hint_start = None

    if self.hint_start is None and blocker == 'none' and self.held_since is not None and i.t - self.held_since >= HELD_FOR:
      if not self.hint_used:
        self.ignored += 1  # the previous hint went unused
      self.hint_start = self.last_hint = i.t
      self.hint_dir = self._side(i)
      self.hint_used = False
      self.lead_hinted = True
      a.count += 1
      a.quiet = self.ignored >= IGNORED_QUIET
      a.chime = not a.quiet
      second = i.lead2 and i.lead2_dist - i.lead_dist < SECOND_CAR and i.lead2_speed < i.lead_speed + 1.0
      a.cars = 2 if second else 1

    a.show = self.hint_start is not None
    a.direction = self.hint_dir if a.show else NONE
    a.blocker = 'none' if a.show else blocker
    return a
