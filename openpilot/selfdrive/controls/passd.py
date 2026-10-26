#!/usr/bin/env python3
"""RehkopfPilot pass hints, as a process: road camera + offline map + the driving model's lead -> passAdvice.

Runs with the van on (PassHints not off). A few times a second it reads the road camera at the model's left and right lane
lines (lane_paint), once a second it matches GPS to the offline map (road_match), and every model frame it asks the
PassAdvisor. It publishes passAdvice for logs, the onroad pill and soundd's soft chime. It never controls the van, and in
factory mode (passive) it only logs.
"""
import time

import numpy as np

import openpilot.cereal.messaging as messaging
from msgq.visionipc import VisionIpcClient
from openpilot.cereal.visionipc import VisionStreamType
from openpilot.cereal import custom, log
from opendbc.car.structs import car
from openpilot.common.gps import get_gps_location_service
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.common.transformations.camera import DEVICE_CAMERAS, view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.selfdrive.controls.lib import lane_paint
from openpilot.selfdrive.controls.lib.pass_advisor import PassAdvisor, PassInputs
from openpilot.selfdrive.navigation.pmtiles import PMTiles
from openpilot.selfdrive.navigation.road_match import RoadMatcher
from openpilot.selfdrive.navigation.tiles import LocalTiles, local_map

READ_EVERY = 5  # model frames between camera readings: 4 a second
MATCH_PERIOD = 1.0  # s between map matches
MATCH_HOLD = 3.0  # s a match stays valid without a new fix
GPS_ACCURACY = 20.0  # m: worse fixes aren't matched
OFF, LEARNING, PILL, CHIME = 0, 1, 2, 3
LINE_KIND = {'unknown': 0, 'dashed_white': 1, 'solid_white': 2, 'yellow': 3}
CALIBRATED = log.ExtrinsicsCalibration.Status.calibrated
Direction = custom.PassAdvice.Direction


def nv12_planes(buf):
  """Y, U and V of an NV12 camera buffer (U and V at half resolution)."""
  w, h, stride, uv_offset = buf.width, buf.height, buf.stride, buf.uv_offset
  data = np.asarray(buf.data, dtype=np.uint8)
  y = data[:stride * h].reshape(h, stride)[:, :w]
  uv = data[uv_offset:uv_offset + stride * (h // 2)].reshape(h // 2, stride)[:, :w]
  return y, uv[:, 0::2], uv[:, 1::2]


class PassD:
  def __init__(self, params, matcher: RoadMatcher | None, passive: bool, gps_service: str = 'gpsLocation'):
    self.params = params
    self.gps_service = gps_service
    self.matcher = matcher
    self.passive = passive
    self.mode = params.get("PassHints", return_default=True)
    self.advisor = PassAdvisor(allow_right=params.get_bool("PassHintsRight"))
    self.votes = (lane_paint.LineVote(), lane_paint.LineVote())
    self.view_from_calib = None
    self.camera = None
    self.road = None
    self.road_time = -1e9
    self.match_time = -1e9
    self.frame = 0
    self.chime_count = 0

  def read_lines(self, model, buf, now: float) -> None:
    """Classify the model's left (1) and right (2) lane lines in a road camera frame."""
    if self.view_from_calib is None or self.camera is None or buf is None or len(model.laneLines) < 3:
      return  # len: no model frame yet at the start of a drive
    y, u, v = nv12_planes(buf)
    scale = (buf.width / self.camera.width, buf.height / self.camera.height)
    for vote, idx in zip(self.votes, (1, 2), strict=True):
      line = model.laneLines[idx]
      points = lane_paint.line_points(np.array(line.x), np.array(line.y), np.array(line.z))
      vote.add(now, lane_paint.read_line(y, u, v, lane_paint.project(points, self.view_from_calib, self.camera.intrinsics, scale),
                                         chroma_scale=2).kind)

  def match_road(self, gps, now: float) -> None:
    if self.matcher is None or now - self.match_time < MATCH_PERIOD:
      return
    self.match_time = now
    if gps.hasFix and gps.horizontalAccuracy < GPS_ACCURACY and gps.speed > 5.0:
      try:
        self.road = self.matcher.match(gps.latitude, gps.longitude, gps.bearingDeg)
        self.road_time = now
      except Exception:
        cloudlog.exception("passd: map match failed")
        self.road = None

  def update(self, sm, buf, now: float):
    """One model frame. `buf` is a road camera frame (or None). Returns the passAdvice message."""
    if sm.updated['extrinsicsCalibration']:
      calib = sm['extrinsicsCalibration']
      if len(calib.rpyCalib) == 3 and calib.calStatus == CALIBRATED:
        self.view_from_calib = view_frame_from_device_frame @ rot_from_euler(list(calib.rpyCalib))
    if self.camera is None and sm.seen['deviceState'] and sm.seen['narrowRoadCameraState']:
      device = DEVICE_CAMERAS.get((str(sm['deviceState'].deviceType), str(sm['narrowRoadCameraState'].sensor)))
      self.camera = device.narrow_road if device else None  # unknown camera: no line readings, so no hints
    if self.frame % READ_EVERY == 0:
      self.read_lines(sm['modelV2'], buf, now)
    self.frame += 1
    self.match_road(sm[self.gps_service], now)

    cs, lead, lead2 = sm['carState'], sm['radarState'].leadOne, sm['radarState'].leadTwo
    if sm['carControl'].longActive and cs.vCruise < 250:
      set_speed = cs.vCruise / 3.6
    elif cs.cruiseState.enabled and cs.cruiseState.speed > 1.0:
      set_speed = cs.cruiseState.speed  # stock cruise (factory mode)
    else:
      set_speed = None
    resolver = sm['longitudinalPlanSP'].speedLimit.resolver
    nav = sm['navInstruction']
    road = self.road if now - self.road_time < MATCH_HOLD else None
    left, right = (vote.kind() if vote.readings and now - vote.readings[-1][0] < 1.0 else 'unknown' for vote in self.votes)
    meta = sm['modelV2'].meta
    a = self.advisor.update(PassInputs(
      t=now, v_ego=cs.vEgo, set_speed=set_speed,
      speed_limit=resolver.speedLimit if resolver.speedLimitValid and resolver.speedLimit > 0 else None,
      lead=lead.present, lead_prob=lead.modelProb, lead_dist=lead.dRel, lead_speed=lead.vLead,
      lead2=lead2.present, lead2_dist=lead2.dRel, lead2_speed=lead2.vLead, left_line=left, right_line=right,
      curvature=sm['modelV2'].action.desiredCurvature, lane_change_state=meta.laneChangeState.raw,
      lane_change_dir=meta.laneChangeDirection.raw, left_blinker=cs.leftBlinker, right_blinker=cs.rightBlinker,
      oneway_road=road is not None and road.oneway, road_kind=road.kind if road else '', ramp=road is not None and road.link,
      nav_distance=nav.maneuverDistance if sm.alive['navInstruction'] and nav.maneuverDistance > 0 else None))

    display = a.show and self.mode >= PILL and not self.passive
    if a.chime and display and self.mode == CHIME:
      self.chime_count += 1

    msg = messaging.new_message('passAdvice')
    pa = msg.passAdvice
    pa.show = a.show
    pa.display = display
    pa.direction = a.direction
    pa.cars = a.cars
    pa.chimeCount = self.chime_count
    pa.count = a.count
    pa.accepted = a.accepted
    pa.quiet = a.quiet
    pa.blocker = a.blocker
    pa.leftLine = LINE_KIND[left]
    pa.rightLine = LINE_KIND[right]
    pa.roadOneway = road is not None and road.oneway
    pa.roadKind = road.kind if road else ''
    pa.mode = self.mode
    return msg


def main():
  params = Params()
  gps_service = get_gps_location_service(params)
  sm = messaging.SubMaster(['modelV2', 'carState', 'carControl', 'radarState', 'longitudinalPlanSP', 'navInstruction',
                            'extrinsicsCalibration', 'deviceState', 'narrowRoadCameraState', gps_service], poll='modelV2')
  pm = messaging.PubMaster(['passAdvice'])
  matcher = None
  if local_map().is_file():
    matcher = RoadMatcher(PMTiles(LocalTiles(local_map())))
  else:
    cloudlog.warning("passd: no offline map, so no road to match and no hints")
  CP = messaging.log_from_bytes(params.get("CarParams", block=True), car.CarParams)
  passd = PassD(params, matcher, passive=CP.passive, gps_service=gps_service)
  vipc = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_NARROW_ROAD, True)
  while True:
    sm.update()
    buf = None
    if passd.frame % READ_EVERY == 0:
      if not vipc.is_connected():
        vipc.connect(False)
      if vipc.is_connected():
        buf = vipc.recv(timeout_ms=20)
    try:
      pm.send('passAdvice', passd.update(sm, buf, time.monotonic()))
    except Exception:
      cloudlog.exception("passd: update failed")  # advice only: skip the frame rather than restart in a loop


if __name__ == "__main__":
  main()
