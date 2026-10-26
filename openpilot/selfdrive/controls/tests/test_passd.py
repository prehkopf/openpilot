"""RehkopfPilot passd: camera frame + map match + model -> passAdvice, and the setting / factory-mode policy."""
from types import SimpleNamespace

import numpy as np

import openpilot.cereal.messaging as messaging
import openpilot.selfdrive.controls.lib.lane_paint as lp
import openpilot.selfdrive.controls.passd as passd
from openpilot.cereal import log
from openpilot.common.constants import CV
from openpilot.common.transformations.camera import DEVICE_CAMERAS, view_frame_from_device_frame
from openpilot.selfdrive.navigation.road_match import RoadMatch

CAM = DEVICE_CAMERAS[('mici', 'os04c10')].narrow_road
W, H = CAM.width, CAM.height
STRIDE = W + 64  # real buffers are padded
LEFT_Y, RIGHT_Y, Z = -1.8, 1.8, 1.2  # lane lines in the calibrated frame (m), road 1.2 m below the camera


def nv12(left_dashed=True):
  """A road frame: grey asphalt with the left lane line drawn dashed (white) where it projects."""
  y = np.full((H, STRIDE), 70, np.uint8)
  uv = np.full((H // 2, STRIDE), 128, np.uint8)
  xs = lp.SAMPLE_X
  pts = np.stack([xs, np.full_like(xs, LEFT_Y), np.full_like(xs, Z)], 1)
  uvs = lp.project(pts, view_frame_from_device_frame, CAM.intrinsics, (1.0, 1.0))
  for i, (u, v) in enumerate(uvs):
    if (left_dashed and i % 4 == 0) or not left_dashed:
      y[int(v) - 3:int(v) + 4, int(u) - 2:int(u) + 3] = 210
  data = np.concatenate([y.ravel(), uv.ravel()])
  return SimpleNamespace(width=W, height=H, stride=STRIDE, uv_offset=STRIDE * H, data=data)


class FakeSM(dict):
  def __init__(self, msgs):
    super().__init__(msgs)
    self.updated = dict.fromkeys(msgs, True)
    self.seen = dict.fromkeys(msgs, True)
    self.alive = dict.fromkeys(msgs, True)
    self.alive['navInstruction'] = False


def sm_stuck(set_kph=105.0, v=52 * CV.MPH_TO_MS, lead_v=52 * CV.MPH_TO_MS):
  msgs = {}
  model = messaging.new_message('modelV2')
  lines = model.modelV2.init('laneLines', 4)
  for line, y in zip(lines, (-5.4, LEFT_Y, RIGHT_Y, 5.4), strict=True):
    line.x = [float(x) for x in np.arange(0, 50, 2.0)]
    line.y = [y] * 25
    line.z = [Z] * 25
  msgs['modelV2'] = model.modelV2
  cs = messaging.new_message('carState')
  cs.carState.vEgo, cs.carState.vCruise = v, set_kph
  msgs['carState'] = cs.carState
  cc = messaging.new_message('carControl')
  cc.carControl.longActive = True
  msgs['carControl'] = cc.carControl
  rs = messaging.new_message('radarState')
  rs.radarState.leadOne.present, rs.radarState.leadOne.modelProb = True, 0.95
  rs.radarState.leadOne.dRel, rs.radarState.leadOne.vLead = 35.0, lead_v
  msgs['radarState'] = rs.radarState
  msgs['longitudinalPlanSP'] = messaging.new_message('longitudinalPlanSP').longitudinalPlanSP
  msgs['navInstruction'] = messaging.new_message('navInstruction').navInstruction
  cal = messaging.new_message('extrinsicsCalibration')
  cal.extrinsicsCalibration.rpyCalib = [0.0, 0.0, 0.0]
  cal.extrinsicsCalibration.calStatus = log.ExtrinsicsCalibration.Status.calibrated
  msgs['extrinsicsCalibration'] = cal.extrinsicsCalibration
  ds = messaging.new_message('deviceState')
  ds.deviceState.deviceType = 'mici'
  msgs['deviceState'] = ds.deviceState
  cam = messaging.new_message('narrowRoadCameraState')
  cam.narrowRoadCameraState.sensor = 'os04c10'
  msgs['narrowRoadCameraState'] = cam.narrowRoadCameraState
  gps = messaging.new_message('gpsLocation')
  gps.gpsLocation.hasFix, gps.gpsLocation.horizontalAccuracy, gps.gpsLocation.speed = True, 3.0, v
  msgs['gpsLocation'] = gps.gpsLocation
  return FakeSM(msgs)


class Matcher:
  def __init__(self, oneway=True):
    self.oneway = oneway

  def match(self, lat, lon, bearing):
    return RoadMatch('highway', 'motorway', self.oneway, False, 3.0, 2.0)


class Params:
  def __init__(self, mode, right=False):
    self.mode, self.right = mode, right

  def get(self, key, return_default=False):
    assert key == 'PassHints'
    return self.mode

  def get_bool(self, key):
    assert key == 'PassHintsRight'
    return self.right


def run(mode, seconds=25, passive=False, oneway=True, left_dashed=True):
  d = passd.PassD(Params(mode), Matcher(oneway), passive=passive)
  sm, buf = sm_stuck(), nv12(left_dashed)
  msgs = [d.update(sm, buf, n * 0.05).passAdvice for n in range(int(seconds / 0.05))]
  return msgs


def test_nv12_planes():
  buf = nv12()
  y, u, v = passd.nv12_planes(buf)
  assert y.shape == (H, W) and u.shape == v.shape == (H // 2, W // 2)
  assert int(u[0, 0]) == int(v[0, 0]) == 128 and y.max() == 210


def test_reads_the_dashed_line_and_hints():
  msgs = run(passd.LEARNING)
  assert msgs[-1].leftLine == 1  # dashedWhite
  assert msgs[-1].roadOneway
  assert any(m.show for m in msgs)


def test_learning_logs_but_never_shows_or_chimes():
  msgs = run(passd.LEARNING)
  assert any(m.show for m in msgs) and not any(m.display for m in msgs) and msgs[-1].chimeCount == 0


def test_pill_shows_without_chime_and_chime_mode_chimes_once():
  msgs = run(passd.PILL)
  assert any(m.display for m in msgs) and msgs[-1].chimeCount == 0
  msgs = run(passd.CHIME)
  assert any(m.display for m in msgs) and msgs[-1].chimeCount == 1


def test_factory_mode_never_shows():
  msgs = run(passd.CHIME, passive=True)
  assert any(m.show for m in msgs) and not any(m.display for m in msgs) and msgs[-1].chimeCount == 0


def test_no_hint_without_the_dashed_line_or_off_a_divided_road():
  assert not any(m.show for m in run(passd.CHIME, left_dashed=False))  # solid line: an edge, not a lane
  assert not any(m.show for m in run(passd.CHIME, oneway=False))


def test_a_crashed_passd_never_blocks_or_ends_engagement():
  # selfdrived raises processNotRunning (no entry, soft disable) for a managed process that died, unless it's ignored
  import ast
  import openpilot.selfdrive.selfdrived.selfdrived as sd
  tree = ast.parse(open(sd.__file__).read())
  ignored = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(getattr(t, "attr", "") == "ignored_processes" for t in n.targets)]
  assert ignored and "passd" in {e.value for e in ignored[0].value.elts}
