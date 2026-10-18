#!/usr/bin/env python3
# Load and run the driving model (stock modeld) and driver monitoring on PC through their real entry points,
# the way the comma does at startup. PC unit tests never start these processes, so a tinygrad / loader
# mismatch only shows up on the device. (2026-10-17: dmonitoringmodeld crashed at load and blocked onboarding.)
import sys
import traceback

import numpy as np

from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.system.camerad.cameras.nv12_info import get_nv12_info

W, H = 1928, 1208
ok = True


class Buf:
  pass


def frame(rng, n):
  b = Buf()
  b.data = rng.integers(0, 256, n, dtype=np.uint8)
  return b


rng = np.random.default_rng(0)
try:
  from openpilot.selfdrive.modeld.dmonitoringmodeld import ModelState as DMState
  dm = DMState(W, H)
  for _ in range(3):
    out, dt = dm.run(frame(rng, dm.frame_buf_params[3]), np.zeros(3, dtype=np.float32), np.eye(3, dtype=np.float32))
  good = out.size > 0 and bool(np.isfinite(out).all())
  print(f"driver monitoring: {out.size} outputs, {dt*1e3:.0f} ms, finite={good}")
  ok &= good
except Exception:
  traceback.print_exc()
  ok = False

try:
  from openpilot.selfdrive.modeld.modeld import ModelState
  m = ModelState(W, H, False)
  m.warmup()
  n = get_nv12_info(W, H)[3]
  dims = {'desire_pulse': ModelConstants.DESIRE_LEN, 'traffic_convention': 2, 'action_t': 2}
  for _ in range(3):
    outs = m.run({k: frame(rng, n) for k in m.vision_input_names}, {k: np.eye(3, dtype=np.float32) for k in m.vision_input_names},
                 {k: np.zeros(v, dtype=np.float32) for k, v in dims.items()})
  good = len(outs) > 0 and all(np.isfinite(v).all() for v in outs.values() if isinstance(v, np.ndarray))
  print(f"driving model: {len(outs)} outputs, finite={good}")
  ok &= good
except Exception:
  traceback.print_exc()
  ok = False

sys.exit(0 if ok else 1)
