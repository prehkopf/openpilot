#!/usr/bin/env python3
# Replay the lead departure chime (sunnypilot E2EAlertsHelper) around recorded e2eChime onsets, with the old sunnypilot
# settings (1 m / 0.3 s, disarm past 8 m) and this build's. Each chime is labelled by what the lead really did in the
# next 4 s (its recorded distance plus how far the van rolled): REAL >= 4 m, creep 1.5-4 m, none < 1.5 m.
# Two replays per chime:
#   as driven:     the recorded drive; the old settings must reproduce the recorded chime (the harness is honest)
#   driver frozen: the van stays stopped (as if nobody reacted), so we see whether and when each setting would chime
# usage: lead_depart_replay.py <rlogs dir> [<route>--<seg> <sec> ...]   (default: the chimes in CHIMES)
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from openpilot.tools.lib.logreader import LogReader
import openpilot.sunnypilot.selfdrive.controls.lib.e2e_alerts_helper as e2e
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP

OLD = {"LEAD_DEPART_DIST_THRESHOLD": 1.0, "LEAD_DEPART_TRIGGER_TIME": 0.3, "LEAD_DEPART_KEEP_ARMED": False}
NEW = {k: getattr(e2e, k) for k in OLD}

# every e2eChime in the drives of 2026-10-17 .. 2026-10-30 (segment, seconds into it by the qlog clock)
CHIMES = """
00000001--7ba2780ebb--14 38.4  00000002--369690c600--6 14.1  00000002--369690c600--21 11.1  00000002--369690c600--84 43.4
00000003--3f2ed0481e--3 37.0  00000005--50a7ee171a--1 54.4  00000005--50a7ee171a--8 38.6  00000006--387f6e3153--3 45.9
00000006--387f6e3153--5 32.6  00000006--387f6e3153--27 12.9  0000000a--a62c125203--7 29.0  0000000b--74d549b913--2 35.2
0000000f--d96284d94b--4 52.2  00000010--8f9b020309--7 24.2  00000012--0b8730db55--9 49.7  00000012--0b8730db55--11 14.5
00000014--fbcacc129e--1 17.6  00000014--fbcacc129e--2 17.7  00000015--795cb2f8a0--6 34.8  00000015--795cb2f8a0--8 22.9
00000018--02ccb58f9a--1 44.8  00000018--02ccb58f9a--2 0.7  00000019--bb6e68a7f5--10 1.2  00000019--bb6e68a7f5--11 21.4
00000019--bb6e68a7f5--12 1.9  00000019--bb6e68a7f5--13 12.0  00000019--bb6e68a7f5--13 43.6  00000019--bb6e68a7f5--14 2.1
00000019--bb6e68a7f5--14 24.7  00000019--bb6e68a7f5--15 56.0  00000019--bb6e68a7f5--16 48.0  00000019--bb6e68a7f5--18 20.5
0000001a--422ba4cf81--51 8.3  0000001a--422ba4cf81--73 32.3  0000001a--422ba4cf81--78 15.2  0000001a--422ba4cf81--108 7.6
0000001d--1ab11c2fb8--4 38.5  0000001f--73812cac14--7 45.2  00000021--2b199bee47--7 20.6  00000021--2b199bee47--60 2.3
00000022--1b51de6164--3 14.8  00000024--b9109612c2--127 1.8  0000003d--db7329abd5--2 16.7  0000003e--f38e2d1248--40 33.3
0000003e--f38e2d1248--45 11.6  0000003e--f38e2d1248--46 41.0  0000003e--f38e2d1248--47 18.1
"""


def default_chimes():
  w = CHIMES.split()
  return list(zip(w[::2], map(float, w[1::2]), strict=True))


def load(rlogs, route, seg):
  """Messages the helper reads from segments seg-2 .. seg+1, in time order, t relative to the start of segment seg."""
  msgs, t_seg = [], None
  for s in range(max(seg - 2, 0), seg + 2):
    fn = os.path.join(rlogs, f"{route}--{s}", "rlog.zst")
    if not os.path.exists(fn):
      continue
    for m in LogReader(fn):
      w = m.which()
      if w == "carState" and s == seg and t_seg is None:
        t_seg = m.logMonoTime * 1e-9
      if w in ("carState", "carControl", "radarState", "modelV2", "onroadEventsSP"):
        msgs.append((m.logMonoTime * 1e-9, w, m.as_builder().as_reader()))
  msgs.sort(key=lambda x: x[0])
  return [(t - t_seg, w, m) for t, w, m in msgs]


def replay(msgs, consts):
  """Chime times (either e2e alert) of the helper run with these module constants over msgs."""
  for k, v in consts.items():
    setattr(e2e, k, v)
  h = e2e.E2EAlertsHelper()
  h._read_params = lambda: None
  h.lead_depart_alert_enabled = True
  h.green_light_alert_enabled = True
  sm, fires = {}, []
  for t, w, m in msgs:
    if w == "onroadEventsSP":
      continue
    sm[w] = getattr(m, w)
    if w == "modelV2" and len(sm) == 4:
      h.update(sm, EventsSP())
      if h.lead_depart_alert or h.green_light_alert:
        fires.append(t)
  return fires


def frozen(msgs, stop_start, t_end):
  """The driver never moves after stop_start: the lead distance becomes the lead's real position (recorded distance
  plus how far the van has rolled since the stop)."""
  out, travel, last_t, v = [], 0.0, None, 0.0
  for t, w, m in msgs:
    if t > t_end:
      break
    if t < stop_start:
      out.append((t, w, m))
    elif w == "carState":
      if last_t is not None:
        travel += v * (t - last_t)
      last_t, v = t, m.carState.vEgo
      b = m.as_builder()
      b.carState.vEgo, b.carState.standstill, b.carState.gasPressed = 0.0, True, False
      out.append((t, w, b.as_reader()))
    elif w == "radarState":
      b = m.as_builder()
      if b.radarState.leadOne.present:
        b.radarState.leadOne.dRel = b.radarState.leadOne.dRel + travel
      out.append((t, w, b.as_reader()))
    else:
      out.append((t, w, m))
  return out


def recorded_onsets(msgs):
  rec, prev = [], False
  for t, w, m in msgs:
    if w != "onroadEventsSP":
      continue
    names = set()
    for e in m.onroadEventsSP.events:
      try:
        names.add(str(e.name))
      except RuntimeError:  # an event this schema doesn't know
        pass
    on = "e2eChime" in names
    if on and not prev:
      rec.append(t)
    prev = on
  return rec


def analyze(job):
  rlogs, segname, t_chime = job
  route, seg = segname.rsplit("--", 1)
  msgs = load(rlogs, route, int(seg))
  rec = recorded_onsets(msgs)
  t_rec = min(rec, key=lambda x: abs(x - t_chime)) if rec else t_chime
  cs = [(t, m.carState.vEgo) for t, w, m in msgs if w == "carState"]
  rs = [(t, m.radarState.leadOne) for t, w, m in msgs if w == "radarState"]
  moving = [t for t, v in cs if v > 0.3]
  stop_start = max([t for t in moving if t < t_rec], default=-1e9)
  stop_end = min([t for t in moving if t > t_rec], default=1e9)

  def rolled(t0, t1):
    pts = [(t, v) for t, v in cs if t0 <= t <= t1]
    return sum(a[1] * (b[0] - a[0]) for a, b in zip(pts, pts[1:], strict=False))

  lead_at = next((lead.dRel for t, lead in rs if t >= t_rec and lead.present), None)
  later = [(t, lead.dRel) for t, lead in rs if t_rec + 3.5 <= t <= t_rec + 4.5 and lead.present]
  moved = later[-1][1] - lead_at + rolled(t_rec, later[-1][0]) if lead_at is not None and later else None
  kind = "lost" if moved is None else "REAL" if moved >= 4.0 else "creep" if moved >= 1.5 else "none"
  cf = frozen(msgs, stop_start, t_rec + 10.0)
  return {"seg": segname, "t": t_rec, "kind": kind, "moved": moved, "lead_at": lead_at, "go": stop_end - t_rec,
          "old_match": any(abs(t - t_rec) < 1.0 for t in replay(msgs, OLD) if stop_start < t < stop_end),
          "old_cf": [t for t in replay(cf, OLD) if t > stop_start], "new_cf": [t for t in replay(cf, NEW) if t > stop_start]}


def run(rlogs, chimes, workers=8):
  jobs = [(rlogs, s, t) for s, t in chimes if os.path.exists(os.path.join(rlogs, s, "rlog.zst"))]
  with ProcessPoolExecutor(workers) as ex:
    return list(ex.map(analyze, jobs))


def summary(res):
  real = [r for r in res if r["kind"] == "REAL"]
  nonreal = [r for r in res if r["kind"] in ("none", "creep")]
  delays = sorted(r["new_cf"][0] - r["old_cf"][0] for r in real if r["old_cf"] and r["new_cf"])
  return {"n": len(res), "old_match": sum(r["old_match"] for r in res), "real": len(real),
          "real_caught": sum(bool(r["new_cf"]) for r in real), "nonreal": len(nonreal),
          "old_false": sum(1 for r in nonreal if r["old_cf"] and r["old_cf"][0] - r["t"] < 4.0),
          "new_false": sum(1 for r in nonreal if r["new_cf"] and r["new_cf"][0] - r["t"] < 4.0),
          "delay_median": delays[len(delays) // 2] if delays else None, "delay_max": delays[-1] if delays else None}


def main(rlogs, args):
  chimes = list(zip(args[::2], map(float, args[1::2]), strict=True)) if args else default_chimes()
  res = run(rlogs, chimes)
  print("segment                  sec  lead ft  lead moved  kind   you went  old replays | driver frozen: old   new  (later)")
  for r in res:
    lead = f"{r['lead_at'] * 3.281:5.1f}" if r["lead_at"] is not None else "  -  "
    moved = f"{r['moved']:5.1f} m" if r["moved"] is not None else "   -   "
    go = f"{r['go']:+5.1f}s" if r["go"] < 1e8 else "  never"
    o = f"{r['old_cf'][0] - r['t']:+5.1f}" if r["old_cf"] else "   - "
    n = f"{r['new_cf'][0] - r['t']:+5.1f}" if r["new_cf"] else "   - "
    d = f"({r['new_cf'][0] - r['old_cf'][0]:+.1f}s)" if r["old_cf"] and r["new_cf"] else ""
    print(f"{r['seg']:24s} {r['t']:5.1f}  {lead}   {moved}   {r['kind']:5s} {go}   {'yes' if r['old_match'] else 'NO '}" +
          f"         | {o} {n} {d}")
  s = summary(res)
  print(f"\nold settings replay {s['old_match']}/{s['n']} recorded chimes")
  print(f"driver frozen: real departures caught {s['real_caught']}/{s['real']}, median {s['delay_median']:+.1f}s later " +
        f"(max {s['delay_max']:+.1f}s); chimes within 4 s when the lead crept or stayed: old {s['old_false']}, " +
        f"new {s['new_false']} of {s['nonreal']}")


if __name__ == "__main__":
  if len(sys.argv) < 2:
    print(__doc__ or "usage: lead_depart_replay.py <rlogs dir> [<route>--<seg> <sec> ...]")
    sys.exit(2)
  main(sys.argv[1], sys.argv[2:])
