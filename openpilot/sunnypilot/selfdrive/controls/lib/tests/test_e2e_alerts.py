"""RehkopfPilot: lead departure chime. It must still chime when the lead really pulls away while we sit stopped, and
must not chime on the two things that set it off falsely in the week of 2026-10-27 (routes 3d, 3e): the vision lead
distance jumping ~1.2 m with nobody moving, and stop-and-go traffic creeping ~2 m and stopping again."""
from types import SimpleNamespace as NS

import pytest

from openpilot.common.realtime import DT_MDL
import openpilot.sunnypilot.selfdrive.controls.lib.e2e_alerts_helper as e2e
from openpilot.sunnypilot.selfdrive.controls.lib.e2e_alerts_helper import E2EAlertsHelper
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP


def sm_frame(v_ego, d_rel):
  return {
    'carState': NS(standstill=v_ego < 0.01, vEgo=v_ego, gasPressed=False),
    'carControl': NS(enabled=False),
    'modelV2': NS(position=NS(x=[0.0] * 33)),
    'radarState': NS(leadOne=NS(present=d_rel is not None, dRel=d_rel if d_rel is not None else 0.0)),
  }


def run(lead_after_stop, gap=3.0):
  """Drive 2 s, stop 3 s behind a lead gap m ahead (arms the alert), then the lead follows lead_after_stop(t).
  Returns how many times the lead departure chime fired."""
  h = E2EAlertsHelper()
  h._read_params = lambda: None
  h.lead_depart_alert_enabled = True
  h.green_light_alert_enabled = True
  chimes = 0
  frames = [(5.0, 20.0)] * int(2 / DT_MDL) + [(0.0, gap)] * int(3 / DT_MDL)
  frames += [(0.0, lead_after_stop(i * DT_MDL)) for i in range(int(6 / DT_MDL))]
  for v, d in frames:
    events = EventsSP()
    h.update(sm_frame(v, d), events)
    chimes += h.lead_depart_alert
  return chimes


def real_departure(t):
  return 3.0 + 2.5 * t  # pulls away at ~5.6 mph


def distance_jump(t):
  return 3.0 if t < 1.0 else 4.2  # route 3e 40:31: 12 -> 16 ft, the car never moved (video)


def creep(t):
  return 3.0 + min(t, 2.0)  # route 3d 2:12: 9 -> 15 ft and stopped again


def brief_spike(t):
  return 7.0 if 1.0 <= t < 1.4 else 3.0  # a 0.4 s misread of the lead distance


def lead_flicker(t):
  return None if 1.0 <= t < 2.0 else 3.7  # the lead drops out for 1 s and comes back where it was


def test_real_departure_chimes_once():
  assert run(real_departure) == 1


@pytest.mark.parametrize("gap", [2.0, 3.0, 3.7, 4.5, 6.0, 7.5])
@pytest.mark.parametrize("speed", [1.0, 2.0, 3.0, 4.0])
def test_departure_chimes_from_any_stop_gap(gap, speed):
  # armed only within 8 m, but it must stay armed while the lead pulls away past 8 m (3 m + 0.5 s takes it there)
  assert run(lambda t: gap + speed * t, gap) == 1


@pytest.mark.parametrize("lead", [distance_jump, creep, brief_spike, lead_flicker])
def test_no_chime_on_jitter_or_creep(lead):
  assert run(lead) == 0


@pytest.mark.parametrize("lead", [distance_jump, creep, brief_spike])
def test_old_thresholds_did_chime(lead, monkeypatch):
  # the scenarios are the ones that fooled the old 1 m / 0.3 s thresholds
  monkeypatch.setattr(e2e, "LEAD_DEPART_DIST_THRESHOLD", 1.0)
  monkeypatch.setattr(e2e, "LEAD_DEPART_TRIGGER_TIME", 0.3)
  assert run(lead) == 1
