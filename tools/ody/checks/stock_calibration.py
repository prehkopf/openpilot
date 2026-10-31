#!/usr/bin/env python3
# Prepush check: calibration and localizer limits stay at comma's values (Ideal). MVL widened them for temporary mounts
# (spread 20/40 deg, INPUT_INVALID_LIMIT 10), which mostly turned off "Device Remount Detected"; a merge could bring that
# back without anyone noticing.
#   1. The limits are comma's, as literals (comparing against the module's own constant can't catch a change to it).
#   2. The van's calibration on the newest pulled drives sits inside them, so the van would still pass.
# Full replay of locationd's bad-input counter and the calibration spread over every drive:
# tools/ody/drive_report/calib_limits.py
# usage: stock_calibration.py <rlogs dir>
import glob
import inspect
import os
import sys

import numpy as np
from openpilot.tools.lib.logreader import LogReader
import openpilot.selfdrive.locationd.calibrationd as calibrationd
import openpilot.selfdrive.locationd.locationd as locationd

MICI_PITCH = [-0.143101, 0.22235988]
YAW = [-0.06912048084718224, 0.06912048084718235]


def main(rlogs):
  fails = []
  if not np.isclose(calibrationd.MAX_ALLOWED_YAW_SPREAD, np.radians(2)):
    fails.append(f"yaw spread limit {np.degrees(calibrationd.MAX_ALLOWED_YAW_SPREAD):.1f} deg, comma's is 2")
  if not np.isclose(calibrationd.MAX_ALLOWED_PITCH_SPREAD, np.radians(4)):
    fails.append(f"pitch spread limit {np.degrees(calibrationd.MAX_ALLOWED_PITCH_SPREAD):.1f} deg, comma's is 4")
  if not np.allclose(calibrationd.YAW_LIMITS, YAW):
    fails.append(f"YAW_LIMITS {calibrationd.YAW_LIMITS}, comma's is {YAW}")
  src = inspect.getsource(calibrationd)
  if "get_device_type() == 'mici'" not in src or "np.array([-0.143101, 0.22235988])" not in src:
    fails.append("comma four (mici) PITCH_LIMITS branch is gone from calibrationd")
  if locationd.INPUT_INVALID_LIMIT != 2.0:
    fails.append(f"locationd INPUT_INVALID_LIMIT {locationd.INPUT_INVALID_LIMIT}, comma's is 2")

  segs = sorted(glob.glob(os.path.join(rlogs, "*--*--*", "qlog.zst")), key=os.path.getmtime)[-100:]
  rpy, spread = [], []
  for fn in segs:
    for m in LogReader(fn):
      if m.which() == "extrinsicsCalibration" and str(m.extrinsicsCalibration.calStatus) == "calibrated":
        rpy.append(m.extrinsicsCalibration.rpyCalib)
        spread.append(m.extrinsicsCalibration.rpyCalibSpread)
  if rpy:
    rpy, spread = np.degrees(np.array(rpy)), np.degrees(np.abs(np.array(spread)))
    print(f"  {len(segs)} newest segments: pitch {rpy[:, 1].min():.2f}..{rpy[:, 1].max():.2f} deg, " +
          f"yaw {rpy[:, 2].min():.2f}..{rpy[:, 2].max():.2f} deg, max spread pitch {spread[:, 1].max():.2f} / yaw {spread[:, 2].max():.2f} deg")
    pitch_lim, yaw_lim = np.degrees(MICI_PITCH), np.degrees(YAW)
    out = np.sum((rpy[:, 1] < pitch_lim[0]) | (rpy[:, 1] > pitch_lim[1]) | (rpy[:, 2] < yaw_lim[0]) | (rpy[:, 2] > yaw_lim[1]))
    over = np.sum((spread[:, 1] > 4) | (spread[:, 2] > 2))
    if out:
      fails.append(f"{out} calibrated messages outside comma's pitch/yaw limits: check the mount")
    if over:
      fails.append(f"{over} calibrated messages over comma's spread limits: the van would see recalibrations")
  else:
    print("  SKIP data part: no calibrated qlogs pulled")
  for f in fails:
    print(f"  FAIL {f}")
  return 1 if fails else 0


if __name__ == "__main__":
  if len(sys.argv) != 2:
    print("usage: stock_calibration.py <rlogs dir>")
    sys.exit(2)
  sys.exit(main(sys.argv[1]))
