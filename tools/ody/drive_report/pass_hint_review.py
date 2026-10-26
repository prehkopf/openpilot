#!/usr/bin/env python3
# Every pass hint passd logged on pulled drives (learning mode included): when, how fast, the car ahead, the line readings,
# the road, and whether a lane change followed. With --frames <dir> and ffmpeg, also a strip of road-camera frames per
# hint (2 s before, at, 3 s and 6 s after; full-res fcamera.hevc when pulled, else qcamera.ts) to check each one by eye.
# usage: pass_hint_review.py <rlogs dir> [route ...] [--frames <out dir>] [--ffmpeg <path>]
import glob
import os
import subprocess
import sys

from openpilot.tools.lib.logreader import LogReader

MPH = 2.23694
LINES = {0: "?", 1: "dashed", 2: "solid", 3: "yellow"}
DIRS = {0: "", 1: "LEFT", 2: "RIGHT"}


def segments(rlogs, route):
  dirs = glob.glob(os.path.join(rlogs, f"{route}--*"))
  return sorted(dirs, key=lambda d: int(d.rsplit("--", 1)[1]))


def hints(seg_dir):
  """Rising edges of passAdvice.show in a segment, with what was going on."""
  out, prev, state = [], False, {}
  t0 = None
  for m in LogReader(os.path.join(seg_dir, "rlog.zst")):
    w = m.which()
    t0 = m.logMonoTime if t0 is None else t0
    if w == "carState":
      state["v"] = m.carState.vEgo
    elif w == "radarState":
      state["lead"] = (m.radarState.leadOne.dRel, m.radarState.leadOne.vLead) if m.radarState.leadOne.present else None
    elif w == "passAdvice":
      pa = m.passAdvice
      if pa.show and not prev:
        out.append({"off": (m.logMonoTime - t0) / 1e9, "dir": DIRS[pa.direction.raw], "cars": pa.cars, "display": pa.display,
                    "mode": pa.mode, "left": LINES[pa.leftLine.raw], "right": LINES[pa.rightLine.raw], "road": pa.roadKind,
                    "oneway": pa.roadOneway, "v": state.get("v", 0.0), "lead": state.get("lead")})
      prev = pa.show
  return out


def frame_strip(seg_dir, off, out_png, ffmpeg):
  video = next((p for p in (os.path.join(seg_dir, "fcamera.hevc"), os.path.join(seg_dir, "qcamera.ts")) if os.path.exists(p)), None)
  if video is None:
    return False
  frames = [max(0, int((off + dt) * 20)) for dt in (-2, 0, 3, 6)]
  select = "+".join(f"eq(n\\,{n})" for n in frames)
  cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", video, "-vf",
         f"select='{select}',scale=480:-1,tile=4x1", "-frames:v", "1", out_png]
  return subprocess.run(cmd, stdin=subprocess.DEVNULL).returncode == 0


def main(argv):
  args = [a for a in argv if not a.startswith("--")]
  frames_dir = argv[argv.index("--frames") + 1] if "--frames" in argv else None
  ffmpeg = argv[argv.index("--ffmpeg") + 1] if "--ffmpeg" in argv else "ffmpeg"
  args = [a for a in args if a not in (frames_dir, ffmpeg)]
  rlogs, routes = args[0], args[1:]
  if not routes:
    routes = sorted({os.path.basename(d).rsplit("--", 1)[0] for d in glob.glob(os.path.join(rlogs, "*--*--*"))})
  total, shown, minutes = 0, 0, 0.0
  for route in routes:
    for seg_dir in segments(rlogs, route):
      if not os.path.exists(os.path.join(seg_dir, "rlog.zst")):
        continue
      minutes += 1
      for h in hints(seg_dir):
        total += 1
        shown += h["display"]
        lead = f"{h['lead'][1] * MPH:3.0f} mph at {h['lead'][0]:3.0f} m" if h["lead"] else "no car ahead"
        seg = os.path.basename(seg_dir)
        road = f"{h['road']}{' one-way' if h['oneway'] else ''}"
        shown_text = "shown" if h["display"] else "logged only"
        print(f"{seg} @{h['off']:4.1f}s: PASS {h['dir']}{' x2' if h['cars'] == 2 else ''}  {h['v'] * MPH:3.0f} mph behind {lead} | " +
              f"lines left {h['left']} right {h['right']} | {road} | {shown_text} (mode {h['mode']})")
        if frames_dir:
          os.makedirs(frames_dir, exist_ok=True)
          if not frame_strip(seg_dir, h["off"], os.path.join(frames_dir, f"{seg}_{h['off']:.0f}s.png"), ffmpeg):
            print("    (no video for this segment)")
  print(f"{total} hints in {minutes / 60:.1f} h of driving ({total / max(minutes / 60, 1e-9):.1f} per hour), {shown} shown")


if __name__ == "__main__":
  main(sys.argv[1:])
