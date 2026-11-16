# ruff: noqa
"""Kennesaw: replay recorded Odyssey drives through this build's Honda CarInterface, today's controller vs the learner.

usage: learner_replay.py <route prefix> <first seg> <last seg> [--load N]
  e.g. learner_replay.py ~/rlogs/00000086--791f5e1d12 22 27

One continuous run over the segments (the learner keeps state across stops; a per-segment replay would restart it).
Feeds the logged CAN to CarInterface.update and the logged carControl / carControlSP to CarInterface.apply, as card
does, twice: OdysseyLearner off and on. Open loop: the van's logged response is used as is, so this shows how the
commands differ on real inputs, not how the van would have moved.
Checks: with the learner off, the gas and accel commands should match what the van logged (carOutput) - that's the
replay's own fidelity check; then, for both, gas/brake domain shares and how far the learner moves the gas command.
--load N: the van load preset (OdysseyLoadPreset) the drive ran with, default 0; it changes the gas map input.
"""
import argparse
import os
from unittest.mock import patch

import numpy as np

from openpilot.tools.lib.logreader import LogReader
from opendbc.car import gen_empty_fingerprint, structs
from opendbc.car.honda.carcontroller import CarController, ODYSSEY_LOAD_FACTORS
from opendbc.car.honda.interface import CarInterface
from openpilot.selfdrive.car.helpers import convert_carControlSP


def segment_files(prefix, first, last):
  out = []
  for n in range(first, last + 1):
    fn = f"{prefix}--{n}/rlog.zst"
    if os.path.isfile(fn):
      out.append(fn)
  return out


def to_struct(cls, msg):
  # openpilot's cereal and opendbc load the same car.capnp, so logged car structs are already the right type
  return msg.as_builder()


def replay(files, learner, load):
  CP = CP_SP = None
  rows = []
  with patch.object(CarController, "_read_odyssey_learner", lambda self: learner), \
       patch.object(CarController, "_read_odyssey_load_factor", lambda self: ODYSSEY_LOAD_FACTORS[load]), \
       patch.object(CarController, "_read_odyssey_rdm_off", lambda self: False):
    CI = None
    cc_sp = None
    logged_out = None
    for fn in files:
      for m in LogReader(fn):
        w = m.which()
        if w == 'carParams' and CI is None:
          CP = to_struct(structs.CarParams, m.carParams)
        elif w == 'carParamsSP' and CI is None and CP is not None:
          # CarParamsSP is a dataclass here; rebuild it from the logged CarParams as card does at startup
          CP_SP = CarInterface.get_params_sp(CP, CP.carFingerprint, gen_empty_fingerprint(), [], CP.openpilotLongitudinalControl,
                                             False, False)
          # get_params also sets the Odyssey's class-level gas map ([-0.2, 2.0] -> [0, 2000]) as on the device
          CarInterface.get_params(CP.carFingerprint, gen_empty_fingerprint(), [], CP.openpilotLongitudinalControl, False, False)
          CI = CarInterface(CP, CP_SP)
          have_can = False
        elif CI is None:
          continue
        elif w == 'can':
          CI.update([(m.logMonoTime, [(c.address, bytes(c.dat), c.src) for c in m.can])])
          have_can = True
        elif w == 'carControlSP':
          cc_sp = convert_carControlSP(m.carControlSP)
        elif w == 'carOutput':
          logged_out = m.carOutput.actuatorsOutput
        elif w == 'carControl' and have_can:
          CC = m.carControl
          out, _ = CI.apply(CC, cc_sp if cc_sp is not None else structs.CarControlSP(), m.logMonoTime)
          c = CI.CC
          rows.append((CC.longActive, CC.actuators.accel, out.gas, out.accel, c.odyssey_gas_selected, c.odyssey_brake_selected,
                       logged_out.gas if logged_out is not None else np.nan, logged_out.accel if logged_out is not None else np.nan))
  return np.array(rows, dtype=float)


def main():
  ap = argparse.ArgumentParser(description="today's Odyssey controller vs the Kennesaw learner on recorded drives")
  ap.add_argument("prefix")
  ap.add_argument("first", type=int)
  ap.add_argument("last", type=int)
  ap.add_argument("--load", type=int, default=0, choices=(0, 1, 2), help="OdysseyLoadPreset the drive ran with")
  a = ap.parse_args()
  prefix, first, last, load = a.prefix, a.first, a.last, a.load
  files = segment_files(prefix, first, last)
  print(f"{os.path.basename(prefix)} segments {first}-{last} ({len(files)} files), load preset {load}")
  off = replay(files, False, load)
  on = replay(files, True, load)
  n = min(len(off), len(on))
  off, on = off[:n], on[:n]
  act = off[:, 0] > 0
  print(f"  frames {n}, openpilot long active {act.sum()} ({act.sum() / 100:.0f} s)")
  # fidelity: today's controller vs what the van logged (the logged carOutput lags the command by one frame)
  gas_diff = np.abs(off[1:, 2] - off[:-1, 6])[act[1:]]
  acc_diff = np.abs(off[1:, 3] - off[:-1, 7])[act[1:]]
  for label, d in (("gas", gas_diff), ("accel", acc_diff)):
    d = d[np.isfinite(d)]
    if len(d):
      print(f"  fidelity, learner off vs logged {label}: median |diff| {np.median(d):.3f}, p99 {np.percentile(d, 99):.3f}, "
            f"exact {np.mean(d < 1e-6) * 100:.1f}%")
  for name, r in (("today", off), ("learner", on)):
    print(f"  {name:8} gas domain {r[act, 4].mean() * 100:5.1f}%  brake domain {r[act, 5].mean() * 100:5.1f}%  "
          f"mean gas {r[act, 2].mean():6.1f}  max gas {r[act, 2].max():6.0f}")
  d = on[act, 2] - off[act, 2]
  print(f"  learner - today, gas command: mean {d.mean():+.1f}, p5 {np.percentile(d, 5):+.1f}, p95 {np.percentile(d, 95):+.1f}, "
        f"max |diff| {np.abs(d).max():.0f} counts; frames differing {np.mean(np.abs(d) > 0.5) * 100:.1f}%")
  dom = np.mean((on[act, 4] != off[act, 4]) | (on[act, 5] != off[act, 5])) * 100
  print(f"  domain choice differs on {dom:.1f}% of active frames")
  # gas -60 is the deliberate coast-bridge command (ODYSSEY_GAS_BRIDGE_COMMAND) in both controllers
  for name, r in (("today", off), ("learner", on)):
    print(f"  {name:8} command range: gas [{r[:, 2].min():.0f}, {r[:, 2].max():.0f}], accel [{r[:, 3].min():+.2f}, {r[:, 3].max():+.2f}]")


if __name__ == "__main__":
  main()
