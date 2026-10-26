"""What the line to the left of the van is painted like: dashed white, solid white, yellow, or unknown.

US markings: a dashed white line separates lanes going the same way; yellow separates opposite directions or marks the left
edge of a divided road; solid white is a road edge or a turn bay. So "dashed white on the left" is the camera's evidence
that the lane to the left is a lane we may move into. The model's lane line positions say where to look; the road camera
image says what is painted there.

Works on one YUV frame (any resolution, with the points projected into it), so it runs on the comma's own camera frames.
"""
from collections import deque
from dataclasses import dataclass

import numpy as np

SAMPLE_X = np.arange(10.0, 34.0, 1.0)  # m ahead along the line: two dash cycles, past where the projection drifts
PEAK_HALF = 3  # px each side of the projected point searched for paint (the projection is good to a few pixels)
REF_HALF = 12  # px each side used as the asphalt reference
PAINT_CONTRAST = 28.0  # luma above the asphalt median that counts as paint
YELLOW_U, YELLOW_V = -10.0, 4.0  # chroma (around 128) of yellow paint: blue-difference low, red-difference up
WHITE_CHROMA = 14.0  # |chroma| below this is neutral (white or grey)
DASHED = (0.12, 0.62)  # share of samples on paint for a dashed line (US: 10 ft dash, 30 ft gap ~ 25%)
SOLID = 0.72


@dataclass
class LineReading:
  kind: str  # 'dashed_white', 'solid_white', 'yellow', 'unknown'
  paint_share: float
  yellow_share: float
  samples: int


def project(points_calib: np.ndarray, view_from_calib: np.ndarray, intrinsics: np.ndarray, scale: tuple[float, float]) -> np.ndarray:
  """Calibrated-frame points (x forward, y right, z down; N x 3) to pixel (u, v) in an image scaled by `scale` (sx, sy)."""
  p = intrinsics @ (view_from_calib @ points_calib.T)
  with np.errstate(divide='ignore', invalid='ignore'):
    return np.stack([p[0] / p[2] * scale[0], p[1] / p[2] * scale[1]], axis=1)


def line_points(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
  """The model's line resampled at SAMPLE_X."""
  if len(x) < 2:
    return np.empty((0, 3))
  keep = (SAMPLE_X >= x[0]) & (SAMPLE_X <= x[-1])
  xs = SAMPLE_X[keep]
  return np.stack([xs, np.interp(xs, x, y), np.interp(xs, x, z)], axis=1)


def read_line(Y: np.ndarray, U: np.ndarray, V: np.ndarray, uv: np.ndarray, chroma_scale: int = 1) -> LineReading:
  """Classify the paint along pixel points `uv` (N x 2). U and V may be subsampled by `chroma_scale` (2 for YUV420)."""
  h, w = Y.shape
  paint = yellow = n = 0
  for u, v in uv:
    if not (np.isfinite(u) and np.isfinite(v)):
      continue
    ui, vi = int(round(u)), int(round(v))
    if not (REF_HALF <= ui < w - REF_HALF and 0 <= vi < h):
      continue
    row = Y[vi, ui - REF_HALF:ui + REF_HALF + 1].astype(np.float32)
    center = row[REF_HALF - PEAK_HALF:REF_HALF + PEAK_HALF + 1]
    asphalt = np.median(np.concatenate([row[:REF_HALF - PEAK_HALF - 1], row[REF_HALF + PEAK_HALF + 2:]]))
    n += 1
    peak = int(np.argmax(center))
    if center[peak] - asphalt < PAINT_CONTRAST:
      continue
    paint += 1
    cu, cv = (ui - PEAK_HALF + peak) // chroma_scale, vi // chroma_scale
    du, dv = float(U[cv, cu]) - 128.0, float(V[cv, cu]) - 128.0
    if du < YELLOW_U and dv > YELLOW_V:
      yellow += 1
  if n < 8:
    return LineReading('unknown', 0.0, 0.0, n)
  share = paint / n
  yellow_share = yellow / paint if paint else 0.0
  if paint >= 3 and yellow_share > 0.5:
    kind = 'yellow'
  elif share >= SOLID:
    kind = 'solid_white'
  elif DASHED[0] <= share <= DASHED[1]:
    kind = 'dashed_white'
  else:
    kind = 'unknown'
  return LineReading(kind, share, yellow_share, n)


VOTE_WINDOW = 3.0  # s of readings (the reader runs a few times a second)
VOTE_MIN = 6  # readings needed in the window
VOTE_DASHED = 0.5  # share of all readings in the window that must be dashed white
VOTE_SOLID = 0.25  # more solid than this and it isn't a line to cross


class LineVote:
  """One reading can be fooled (in shade and far off, yellow paint can look white); a few seconds of readings rarely are.
  Dashed white needs half of all readings (unsure ones count against it), and a single yellow reading vetoes it."""
  def __init__(self):
    self.readings: deque[tuple[float, str]] = deque()

  def add(self, t: float, kind: str) -> None:
    self.readings.append((t, kind))
    while t - self.readings[0][0] > VOTE_WINDOW:
      self.readings.popleft()

  def kind(self) -> str:
    n = len(self.readings)
    if n < VOTE_MIN:
      return 'unknown'
    count = dict.fromkeys(('dashed_white', 'solid_white', 'yellow', 'unknown'), 0)
    for _, k in self.readings:
      count[k] += 1
    if count['yellow']:
      return 'yellow'
    if count['solid_white'] > VOTE_SOLID * n:
      return 'solid_white'
    if count['dashed_white'] >= VOTE_DASHED * n:
      return 'dashed_white'
    return 'unknown'
