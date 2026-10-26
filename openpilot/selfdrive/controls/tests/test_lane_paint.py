"""RehkopfPilot pass hints: reading the line beside the van from the road camera image."""
import numpy as np

import openpilot.selfdrive.controls.lib.lane_paint as lp
from openpilot.common.transformations.camera import DEVICE_CAMERAS, view_frame_from_device_frame

H, W = 200, 300
ASPHALT, PAINT = 70, 200
U_YELLOW, V_YELLOW = 128 - 40, 128 + 25  # yellow: blue-difference low, red-difference up
POINTS = np.array([(150.0, v) for v in range(40, 190, 6)])  # 25 points down a column, like a line in the image


def image(pattern, yellow=False):
  """A line along POINTS. pattern(i) says whether the i-th point is painted (dashes, solid, nothing)."""
  Y = np.full((H, W), ASPHALT, np.uint8)
  U = np.full((H, W), 128, np.uint8)
  V = np.full((H, W), 128, np.uint8)
  for i, (u, v) in enumerate(POINTS):
    if pattern(i):
      Y[int(v) - 3:int(v) + 4, int(u) - 1:int(u) + 2] = PAINT
      if yellow:
        U[int(v) - 3:int(v) + 4, int(u) - 1:int(u) + 2] = U_YELLOW
        V[int(v) - 3:int(v) + 4, int(u) - 1:int(u) + 2] = V_YELLOW
  return Y, U, V


def read(pattern, yellow=False, points=POINTS):
  return lp.read_line(*image(pattern, yellow), points, chroma_scale=1)


def dashed(i):
  return i % 4 == 0  # 25% painted, like 10 ft dashes with 30 ft gaps


def solid(i):
  return True


def test_line_kinds():
  assert read(dashed).kind == 'dashed_white'
  assert read(solid).kind == 'solid_white'
  assert read(solid, yellow=True).kind == 'yellow'
  assert read(dashed, yellow=True).kind == 'yellow'  # a dashed yellow center line is still yellow
  assert read(lambda i: False).kind == 'unknown'


def test_paint_is_found_a_few_pixels_off_the_projection():
  off = POINTS + (lp.PEAK_HALF, 0)
  assert read(dashed, points=off).kind == 'dashed_white'


def test_too_few_points_on_the_image_is_unknown():
  assert read(solid, points=POINTS[:5]).kind == 'unknown'
  outside = POINTS + (W, 0)  # projected off the side of the image
  assert read(solid, points=outside).kind == 'unknown'


def test_projection_puts_a_point_straight_ahead_near_the_image_center():
  cam = DEVICE_CAMERAS[('mici', 'os04c10')].narrow_road
  uv = lp.project(np.array([[30.0, 0.0, 0.0]]), view_frame_from_device_frame, cam.intrinsics, (1.0, 1.0))
  assert abs(uv[0, 0] - cam.width / 2) < 1 and abs(uv[0, 1] - cam.height / 2) < 1
  # a point to the right (y > 0 in the device frame) lands right of center
  right = lp.project(np.array([[30.0, 2.0, 0.0]]), view_frame_from_device_frame, cam.intrinsics, (1.0, 1.0))
  assert right[0, 0] > cam.width / 2


def vote(kinds, dt=0.25):
  v = lp.LineVote()
  for n, k in enumerate(kinds):
    v.add(n * dt, k)
  return v.kind()


def test_vote_needs_half_of_all_readings_dashed():
  assert vote(['dashed_white'] * 7 + ['unknown'] * 5) == 'dashed_white'
  # route 21, a raised median's yellow edge read as dashed twice among unsure readings: not enough
  assert vote(['unknown'] * 11 + ['dashed_white'] * 2) == 'unknown'


def test_one_yellow_reading_vetoes():
  assert vote(['dashed_white'] * 11 + ['yellow']) == 'yellow'


def test_mostly_solid_is_solid():
  assert vote(['dashed_white'] * 8 + ['solid_white'] * 4) == 'solid_white'


def test_vote_window_and_minimum():
  assert vote(['dashed_white'] * 4) == 'unknown'  # too few readings yet
  v = lp.LineVote()
  v.add(0.0, 'yellow')
  for n in range(1, 13):
    v.add(lp.VOTE_WINDOW + n * 0.25, 'dashed_white')
  assert v.kind() == 'dashed_white'  # the old yellow reading aged out
