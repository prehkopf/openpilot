"""RehkopfPilot pass hints: when a hint shows, and the many times it must stay quiet."""
from dataclasses import replace

import openpilot.selfdrive.controls.lib.pass_advisor as pa
from openpilot.common.constants import CV

MPH = CV.MPH_TO_MS
DT = 0.1


def stuck(**kw):
  """65 mph set, 52 mph car 35 m ahead, on an interstate carriageway, dashed white line on the left."""
  base = pa.PassInputs(t=0.0, v_ego=52 * MPH, set_speed=65 * MPH, speed_limit=None, lead=True, lead_prob=0.95, lead_dist=35.0,
                       lead_speed=52 * MPH, lead2=False, lead2_dist=0.0, lead2_speed=0.0, left_line='dashed_white',
                       right_line='solid_white', curvature=0.0, lane_change_state=0, lane_change_dir=0, left_blinker=False,
                       right_blinker=False, oneway_road=True, road_kind='highway', ramp=False, nav_distance=None)
  return replace(base, **kw)


def drive(adv, seconds, t0=0.0, **kw):
  """Advice at every 0.1 s step."""
  out = []
  for n in range(int(seconds / DT)):
    a = adv.update(stuck(t=t0 + n * DT, **kw))
    out.append((a.show, a.chime, a.direction, a.cars, a.blocker))
  return out


def first_hint(steps):
  return next((n * DT for n, s in enumerate(steps) if s[0]), None)


def test_hint_after_being_held_back():
  steps = drive(pa.PassAdvisor(), 30)
  t = first_hint(steps)
  assert t is not None and abs(t - 10.0) < 0.5  # 10 s behind the slow car (a literal: a test reading HELD_FOR can't catch a change to it)
  show, chime, direction, cars, _ = steps[int(t / DT)]
  assert chime and direction == pa.LEFT and cars == 1
  # it stays up SHOW_FOR, then goes away and doesn't come back for the same car
  assert sum(s[0] for s in steps) <= pa.SHOW_FOR / DT + 1
  assert not steps[-1][0] and steps[-1][4] == 'already_hinted'


def test_no_hint_without_a_lane_to_move_into():
  for line in ('yellow', 'solid_white', 'unknown'):
    assert first_hint(drive(pa.PassAdvisor(), 30, left_line=line)) is None, line


def test_no_hint_on_two_way_roads_ramps_or_side_streets():
  assert first_hint(drive(pa.PassAdvisor(), 30, oneway_road=False)) is None
  assert first_hint(drive(pa.PassAdvisor(), 30, ramp=True)) is None
  assert first_hint(drive(pa.PassAdvisor(), 30, road_kind='minor_road')) is None


def test_no_hint_when_it_isnt_worth_it():
  # 3 mph slower: about 6 s saved over 2 miles, under MIN_GAIN
  assert first_hint(drive(pa.PassAdvisor(), 30, lead_speed=62 * MPH, v_ego=62 * MPH)) is None
  # with a known limit, a car at or near the limit is not slow, whatever the set speed
  assert first_hint(drive(pa.PassAdvisor(), 30, speed_limit=55 * MPH)) is None
  assert first_hint(drive(pa.PassAdvisor(), 30, speed_limit=70 * MPH)) is not None


def test_no_hint_in_calm_conditions_that_are_not():
  assert first_hint(drive(pa.PassAdvisor(), 30, v_ego=35 * MPH, lead_speed=30 * MPH)) is None  # too slow for passing
  assert first_hint(drive(pa.PassAdvisor(), 30, curvature=1 / 200)) is None  # 52 mph in a 200 m curve
  steps = drive(pa.PassAdvisor(), 30, nav_distance=1000.0)  # exit coming up
  assert first_hint(steps) is None and steps[-1][4] == 'turn'  # for that reason (the gain math alone would also block it)
  assert first_hint(drive(pa.PassAdvisor(), 30, left_blinker=True)) is None


def test_the_car_has_to_be_in_the_way():
  assert first_hint(drive(pa.PassAdvisor(), 30, lead_dist=90.0)) is None  # 3.9 s ahead: not following
  assert first_hint(drive(pa.PassAdvisor(), 30, lead_prob=0.4)) is None


def test_driving_yourself_uses_your_own_speed():
  adv = pa.PassAdvisor()
  # a minute of open road at 66 mph, then stuck behind a 52 mph car with no cruise set
  drive(adv, 60, set_speed=None, lead=False, v_ego=66 * MPH)
  steps = drive(adv, 30, t0=60.0, set_speed=None)
  assert first_hint(steps) is not None
  # with no history of the driver's own speed there's nothing to compare with
  assert first_hint(drive(pa.PassAdvisor(), 30, set_speed=None)) is None


def test_two_slow_cars():
  steps = drive(pa.PassAdvisor(), 30, lead2=True, lead2_dist=70.0, lead2_speed=51 * MPH)
  assert steps[int(first_hint(steps) / DT)][3] == 2
  # a second car far ahead or faster isn't part of this pass
  steps = drive(pa.PassAdvisor(), 30, lead2=True, lead2_dist=300.0, lead2_speed=51 * MPH)
  assert steps[int(first_hint(steps) / DT)][3] == 1


def test_left_lane_camper_only_when_allowed():
  # in the left lane (yellow on the left, dashed on the right) behind a slow car
  kw = {'left_line': 'yellow', 'right_line': 'dashed_white'}
  assert first_hint(drive(pa.PassAdvisor(), 30, **kw)) is None
  steps = drive(pa.PassAdvisor(allow_right=True), 30, **kw)
  assert first_hint(steps) is not None and steps[int(first_hint(steps) / DT)][2] == pa.RIGHT


def test_backs_off_after_unused_hints():
  adv = pa.PassAdvisor()
  t, chimes = 0.0, []
  for _ in range(5):
    steps = drive(adv, 12, t0=t)  # a new slow car each time (the gap jumps), never passed
    t += 12
    drive(adv, 0.2, t0=t, lead=False)  # the car ahead turns off
    t += 0.2
    drive(adv, pa.MIN_INTERVAL, t0=t, lead=False)
    t += pa.MIN_INTERVAL
    chimes += [s[1] for s in steps if s[1]]
  assert len(chimes) == pa.IGNORED_QUIET  # after that many unused hints, the pill shows without a chime
  assert adv.advice.quiet and adv.advice.count == 5


def test_a_used_hint_resets_the_quiet_count():
  adv = pa.PassAdvisor()
  steps = drive(adv, 11)
  assert any(s[0] for s in steps)
  adv.update(stuck(t=11.0, lane_change_state=pa.LANE_CHANGE_STARTING, lane_change_dir=pa.LEFT))
  assert adv.advice.accepted == 1 and adv.ignored == 0 and not adv.advice.show


def test_hint_goes_away_when_things_change():
  adv = pa.PassAdvisor()
  steps = drive(adv, pa.HELD_FOR + 1)
  assert steps[-1][0]
  adv.update(stuck(t=pa.HELD_FOR + 1, left_line='yellow'))  # the dashed line ended
  assert not adv.advice.show
