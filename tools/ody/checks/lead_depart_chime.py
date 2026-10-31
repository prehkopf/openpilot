#!/usr/bin/env python3
# Prepush check: lead departure chime (Ideal). Replays the chime over the 47 recorded e2eChimes of 2026-10-17 .. 10-30
# (tools/ody/drive_report/lead_depart_replay.py).
#   1. The old sunnypilot settings must reproduce the recorded chimes (the harness is honest).
#   2. With the driver frozen at the stop, this build must still chime on every real departure.
#   3. ... and chime within 4 s on at most a quarter of the stops where the lead only crept or stayed (old: all of them).
# usage: lead_depart_chime.py <rlogs dir>
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "drive_report"))
import lead_depart_replay


def main(rlogs):
  chimes = [(s, t) for s, t in lead_depart_replay.default_chimes() if os.path.exists(os.path.join(rlogs, s, "rlog.zst"))]
  if len(chimes) < 20:
    print(f"  SKIP only {len(chimes)} of the recorded chimes are pulled")
    return 0
  s = lead_depart_replay.summary(lead_depart_replay.run(rlogs, chimes, workers=4))
  print(f"  old settings replay {s['old_match']}/{s['n']} recorded chimes; driver frozen: real departures caught " +
        f"{s['real_caught']}/{s['real']} (median {s['delay_median']:+.1f}s later), false chimes within 4 s " +
        f"old {s['old_false']} new {s['new_false']} of {s['nonreal']}")
  fails = []
  if s["old_match"] < 0.9 * s["n"]:
    fails.append(f"old settings replay only {s['old_match']}/{s['n']} recorded chimes: the harness or the helper's inputs changed")
  if s["real_caught"] < s["real"]:
    fails.append(f"real departures caught {s['real_caught']}/{s['real']}: a lead that really leaves must always chime")
  if s["new_false"] > 0.25 * s["nonreal"]:
    fails.append(f"{s['new_false']}/{s['nonreal']} chimes on a lead that only crept or stayed, want at most a quarter")
  for f in fails:
    print(f"  FAIL {f}")
  return 1 if fails else 0


if __name__ == "__main__":
  if len(sys.argv) != 2:
    print("usage: lead_depart_chime.py <rlogs dir>")
    sys.exit(2)
  sys.exit(main(sys.argv[1]))
