#!/usr/bin/env python3
# Prepush check: factory mode must leave the van stock. Replays this build's card on a recorded Odyssey segment
# twice. With FactoryMode=0 card must take control (not passive, Honda safety, sends CAN), which proves the replay
# reaches the point where the radar is silenced. With FactoryMode=1 card must be passive, in noOutput safety (so the
# harness relay stays with the stock camera), and send nothing at all: no radar silence, no steering, no ACC.
# Openpilot longitudinal stays set in both, so ExperimentalMode and DEC aren't cleared by a factory drive.
# usage: factory_mode.py <segment dir or rlog.zst>
import os
import sys

from opendbc.car.structs import car
from openpilot.selfdrive.test.process_replay.process_replay import replay_process_with_name
from openpilot.tools.lib.logreader import LogReader

NO_OUTPUT = car.CarParams.SafetyModel.noOutput


def run_card(lr, factory: bool):
  out = replay_process_with_name("card", lr, disable_progress=True,
                                 custom_params={"FactoryMode": factory, "AlphaLongitudinalEnabled": True})
  cp = next(m.carParams for m in out if m.which() == "carParams")
  sent = sum(len(m.sendcan) for m in out if m.which() == "sendcan")
  return cp, sent


def main(seg):
  lr = list(LogReader(os.path.join(seg, "rlog.zst") if os.path.isdir(seg) else seg))
  fails = []

  cp, sent = run_card(lr, factory=False)
  safety = [s.safetyModel for s in cp.safetyConfigs]
  print(f"  RehkopfPilot: passive={cp.passive} long={cp.openpilotLongitudinalControl} safety={safety} CAN sent={sent}")
  if cp.passive or NO_OUTPUT in safety or sent == 0:
    fails.append("baseline: card did not take control, so this check proves nothing")

  cp, sent = run_card(lr, factory=True)
  safety = [s.safetyModel for s in cp.safetyConfigs]
  print(f"  factory:      passive={cp.passive} long={cp.openpilotLongitudinalControl} safety={safety} CAN sent={sent}")
  if not cp.passive:
    fails.append("factory: card is not passive")
  if safety != [NO_OUTPUT]:
    fails.append(f"factory: safety {safety}, want [noOutput] (relay must stay with the stock camera)")
  if sent:
    fails.append(f"factory: card sent {sent} CAN messages (radar silence / controls), want 0")
  if not cp.openpilotLongitudinalControl:
    fails.append("factory: openpilotLongitudinalControl cleared; selfdrived and the UI would delete ExperimentalMode/DEC")

  for f in fails:
    print(f"  FAIL {f}")
  return 1 if fails else 0


if __name__ == "__main__":
  if len(sys.argv) != 2:
    sys.exit("usage: factory_mode.py <segment dir or rlog.zst>")
  sys.exit(main(sys.argv[1]))
