# Run the green-light launch module over whole recorded drives: where would it fire, how much would it ask for,
# and was anything close in front when it did? (offline, from logged carState / modelV2 / plan / DEC state)
# usage: launch_eval.py <route prefix> [<route prefix> ...]
import glob
import sys
from concurrent.futures import ProcessPoolExecutor

from openpilot.selfdrive.controls.lib.launch_boost import GreenLightLaunch
from openpilot.tools.lib.logreader import LogReader

ACTION_T = 0.55


def read_seg(fn):
  out = []
  st = {"cs": None, "e2e": False, "plan_a": 0.0, "long": False, "lead": None}
  try:
    for m in LogReader(fn):
      w = m.which()
      if w == "carState":
        st["cs"] = (m.carState.standstill, m.carState.vEgo, m.carState.aEgo, m.carState.gasPressed)
      elif w == "selfdriveState":
        st["exp"] = m.selfdriveState.experimentalMode
      elif w == "longitudinalPlanSP":
        dec = m.longitudinalPlanSP.dec
        st["e2e"] = st.get("exp", False) and (not dec.active or str(dec.state) == "blended")
      elif w == "longitudinalPlan":
        st["plan_a"] = m.longitudinalPlan.aTarget
      elif w == "carControl":
        st["long"] = m.carControl.longActive
      elif w == "radarState":
        lo = m.radarState.leadOne
        st["lead"] = (lo.dRel, lo.vLead) if lo.present else None
      elif w == "modelV2" and st["cs"] is not None:
        md = m.modelV2
        out.append((m.logMonoTime * 1e-9, *st["cs"], st["e2e"], st["long"], md.action.desiredAcceleration, md.action.shouldStop,
                    list(md.velocity.x), list(md.acceleration.x), st["plan_a"], st["lead"]))
  except Exception as e:
    print(f"  ! {fn}: {type(e).__name__}: {e}"[:160])
  return out


def main():
  total_active, firing = 0, []
  for prefix in sys.argv[1:]:
    files = sorted(glob.glob(f"{prefix}--*/rlog.zst"), key=lambda f: int(f.split("--")[-1].split("/")[0]))
    with ProcessPoolExecutor() as ex:
      rows = [r for seg in ex.map(read_seg, files) for r in seg]
    if not rows:
      continue
    g = GreenLightLaunch()
    t0, episode = rows[0][0], None
    for t, standstill, v, _a, gas, e2e, long_on, a_e2e, stop, mv, ma, plan_a, lead in rows:
      boosted = g.update(standstill, v, e2e, a_e2e, stop, mv, ma, ACTION_T)
      if g.active and long_on:
        total_active += 1
        if episode is None:
          episode = {"t": t - t0, "route": prefix.rsplit("/", 1)[-1], "asks": [], "e2e": [], "plan": [], "lead": lead, "gas": False,
                     "v_end": v}
        episode["asks"].append(boosted)
        episode["e2e"].append(a_e2e)
        episode["plan"].append(plan_a)
        episode["gas"] |= gas
        episode["v_end"] = v
      elif episode is not None and not g.active:
        firing.append(episode)
        episode = None
    if episode is not None:
      firing.append(episode)
  print(f"model frames with launch active (op long on): {total_active} ({total_active * 0.05:.1f} s)")
  for e in firing:
    lead = f"lead {e['lead'][0]:.0f} m @ {e['lead'][1] * 2.237:.0f} mph" if e["lead"] else "no lead"
    print(f"  {e['route']} {e['t'] / 60:6.1f} min | {len(e['asks']) * 0.05:3.1f} s | model asked {max(e['e2e']):.2f} -> launch asks " +
          f"{max(e['asks']):.2f} | logged plan max {max(e['plan']):.2f} | ended at {e['v_end'] * 2.237:.1f} mph | {lead} | gas {e['gas']}")


if __name__ == "__main__":
  main()
