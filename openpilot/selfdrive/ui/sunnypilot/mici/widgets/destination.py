"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.mici.widgets.button import BigMultiToggle

NONE = "none"


def favorites(params) -> list[dict]:
  """Saved places (param NavFavorites): [{"name", "latitude", "longitude"}, ...], skipping malformed entries."""
  saved = params.get("NavFavorites")
  if not isinstance(saved, list):
    return []
  good = []
  for place in saved:
    try:
      name, lat, lon = str(place["name"]).strip(), float(place["latitude"]), float(place["longitude"])
    except (KeyError, TypeError, ValueError):
      continue
    if name and name != NONE and -90 <= lat <= 90 and -180 <= lon <= 180:
      good.append({"name": name, "latitude": lat, "longitude": lon})
  return good


def selected(params, places: list[dict]) -> str:
  """The saved place NavDestination points at, or none."""
  dest = params.get("NavDestination")
  if isinstance(dest, dict):
    for place in places:
      if abs(place["latitude"] - dest.get("latitude", 999)) < 1e-6 and abs(place["longitude"] - dest.get("longitude", 999)) < 1e-6:
        return place["name"]
  return NONE


class DestinationToggle(BigMultiToggle):
  """comma four picker for a saved destination: sets the route navd follows (and turns navigation on)."""
  def __init__(self):
    super().__init__("destination", [NONE], select_callback=self._on_select,
                     description="Route to a saved place. Use it for openpilot's route\n" +
                                 "awareness; keep your phone for traffic rerouting.\n" +
                                 "Cleared when the car turns off.")
    self._params = Params()
    self._places: list[dict] = []
    self.refresh()
    self.set_visible(lambda: bool(self._places))

  def refresh(self):
    self._places = favorites(self._params)
    self._options = [NONE] + [p["name"] for p in self._places]
    self.set_value(selected(self._params, self._places))

  def _on_select(self, label: str):
    place = next((p for p in self._places if p["name"] == label), None)
    if place is None:
      self._params.remove("NavDestination")
      return
    self._params.put_bool("NavigationEnabled", True)
    self._params.put("NavDestination", {"latitude": place["latitude"], "longitude": place["longitude"]})
