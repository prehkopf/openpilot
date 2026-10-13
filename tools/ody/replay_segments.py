#!/usr/bin/env python3
# Replay card + controlsd from this checkout on recorded Odyssey segments and sanity-check the outputs.
# usage: replay_segments.py <segment dir or rlog.zst> [...]
#   e.g. replay_segments.py ~/rlogs/00000008--83edc4fea4--10
import os
import sys
import numpy as np
from openpilot.tools.lib.logreader import LogReader
from openpilot.selfdrive.test.process_replay.process_replay import replay_process_with_name, check_most_messages_valid


def rlog_path(arg):
  return os.path.join(arg, "rlog.zst") if os.path.isdir(arg) else arg


def main(args):
  if not args:
    sys.exit("usage: replay_segments.py <segment dir or rlog.zst> [...]")
  for seg in args:
    lr = list(LogReader(rlog_path(seg)))
    rec_cs = [m.carState for m in lr if m.which() == "carState"]
    rec_cc = [m.carControl for m in lr if m.which() == "carControl"]
    print(f"===== {seg}: {len(lr)} msgs, recorded carState {len(rec_cs)} =====")
    for proc in ("card", "controlsd"):
      try:
        out = replay_process_with_name(proc, lr, disable_progress=True)
      except Exception as e:
        print(f"  {proc}: CRASH {type(e).__name__}: {str(e)[:300]}")
        continue
      kinds = {}
      for m in out:
        kinds[m.which()] = kinds.get(m.which(), 0) + 1
      # the card message count varies run to run in the replay harness; compare values, not counts
      print(f"  {proc}: {len(out)} msgs {kinds} valid={check_most_messages_valid(out)}")
      if proc == "card":
        cp = next((m.carParams for m in out if m.which() == "carParams"), None)
        if cp is not None:
          safety = [(s.safetyModel, s.safetyParam) for s in cp.safetyConfigs]
          print(f"    CP {cp.carFingerprint} long={cp.openpilotLongitudinalControl} delay={cp.longitudinalActuatorDelay:.2f} safety={safety}")
        cs = [m.carState for m in out if m.which() == "carState"]
        if len(cs) == len(rec_cs):  # only aligned when the harness kept every frame
          dv = np.abs(np.array([c.vEgo for c in cs]) - np.array([c.vEgo for c in rec_cs]))
          print(f"    vEgo vs recorded: max diff {dv.max():.3f} m/s")
        print(f"    vEgo range {min(c.vEgo for c in cs):.1f}..{max(c.vEgo for c in cs):.1f} m/s " +
              f"(recorded {min(c.vEgo for c in rec_cs):.1f}..{max(c.vEgo for c in rec_cs):.1f})")
        sendcan = [m for m in out if m.which() == "sendcan"]
        print(f"    sendcan frames with msgs: {sum(1 for m in sendcan if len(m.sendcan))}/{len(sendcan)}")
      else:
        cc = [m.carControl for m in out if m.which() == "carControl"]
        if cc:
          acc = np.array([c.actuators.accel for c in cc])
          rec_acc = np.array([c.actuators.accel for c in rec_cc[:len(cc)]])
          tq = np.array([c.actuators.torque for c in cc])
          n = min(len(acc), len(rec_acc))
          print(f"    enabled {sum(c.enabled for c in cc)}/{len(cc)}; accel range {acc.min():.2f}..{acc.max():.2f} " +
                f"(recorded {rec_acc.min():.2f}..{rec_acc.max():.2f}); mean |accel - recorded| {np.abs(acc[:n] - rec_acc[:n]).mean():.3f}; " +
                f"torque range {tq.min():.2f}..{tq.max():.2f}")


if __name__ == "__main__":
  main(sys.argv[1:])
