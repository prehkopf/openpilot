#!/usr/bin/env python3
# Print the Honda tuning this checkout builds (delay, ki), and optionally what recorded drives actually ran.
# usage: check_params.py [segment dir or rlog.zst ...]
import os
import sys
from opendbc.car import gen_empty_fingerprint
from opendbc.car.car_helpers import interfaces
from opendbc.car.honda.values import CAR
from openpilot.tools.lib.logreader import LogReader


def built():
  for car in (CAR.HONDA_CIVIC, CAR.HONDA_ACCORD, CAR.HONDA_ODYSSEY_5G_MMR):
    for long in (False, True):
      CP = interfaces[car].get_params(car, gen_empty_fingerprint(), [], long, False, False)
      t = CP.longitudinalTuning
      print(f"{car} {'op long' if long else 'stock long'}: delay {CP.longitudinalActuatorDelay} kiBP {list(t.kiBP)} kiV {list(t.kiV)}")


def recorded(paths):
  for p in paths:
    lr = LogReader(os.path.join(p, "rlog.zst") if os.path.isdir(p) else p)
    cp = init = None
    for m in lr:
      if m.which() == "carParams" and cp is None:
        cp = m.carParams
      elif m.which() == "initData" and init is None:
        init = m.initData
      if cp is not None and init is not None:
        break
    print(p, cp.carFingerprint if cp else None, "delay", round(cp.longitudinalActuatorDelay, 3) if cp else None,
          init.gitRemote if init else "?", init.gitBranch if init else "?")


if __name__ == "__main__":
  built()
  recorded(sys.argv[1:])
