"""Which road the van is on, from a GPS fix and the offline map (RehkopfPilot pass hints).

OSM maps a divided road as two one-way ways, one per carriageway, each drawn in the direction of travel. So a match to a
one-way way whose direction agrees with the van's heading means every lane beside us carries traffic our way: a lane to the
left is a passing lane, never oncoming traffic. The heading check also keeps a fix that is a few meters off from matching
the opposite carriageway.
"""
import math
from dataclasses import dataclass

import numpy as np

from openpilot.selfdrive.navigation.pmtiles import PMTiles
from openpilot.selfdrive.navigation.vector_tile import Road, decode_roads

ZOOM = 15  # the extract's most detailed level
EARTH_CIRCUMFERENCE = 40075016.686  # m
MAX_DISTANCE = 20.0  # m from the road's centerline; a multi-lane carriageway's lanes sit within ~10 m of it
MAX_HEADING_ERROR = 35.0  # deg
HEADING_WEIGHT = 0.3  # m of distance per degree of heading error when picking between nearby roads
CACHE_TILES = 16


@dataclass(frozen=True)
class RoadMatch:
  kind: str  # Protomaps kind: highway, major_road, minor_road, other
  detail: str  # the OSM highway type: motorway, trunk, primary, ...
  oneway: bool  # one carriageway of a divided road (or a one-way street)
  link: bool  # a ramp
  distance: float  # m from the road
  heading_error: float  # deg between the van's heading and the road's direction


def tile_coords(lat: float, lon: float, zoom: int = ZOOM) -> tuple[float, float]:
  """Web Mercator tile coordinates (fractional): x east, y south."""
  n = 2 ** zoom
  return (lon + 180.0) / 360.0 * n, (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n


def angle_diff(a: float, b: float) -> float:
  return abs((a - b + 180.0) % 360.0 - 180.0)


class RoadMatcher:
  def __init__(self, archive: PMTiles):
    self.archive = archive
    self._tiles: dict[tuple[int, int], list[Road]] = {}

  def _roads(self, x: int, y: int) -> list[Road]:
    if (x, y) not in self._tiles:
      data = self.archive.get(ZOOM, x, y)
      self._tiles[(x, y)] = decode_roads(data) if data else []
      if len(self._tiles) > CACHE_TILES:
        self._tiles.pop(next(iter(self._tiles)))
    return self._tiles[(x, y)]

  def match(self, lat: float, lon: float, bearing: float) -> RoadMatch | None:
    """The road under a fix heading `bearing` (deg clockwise from north), or None off the map or between roads."""
    fx, fy = tile_coords(lat, lon)
    tx, ty = math.floor(fx), math.floor(fy)
    tile_m = EARTH_CIRCUMFERENCE * math.cos(math.radians(lat)) / 2 ** ZOOM
    reach = MAX_DISTANCE / tile_m
    best, best_score = None, math.inf
    for dx in (-1, 0, 1):
      if (dx == -1 and fx - tx > reach) or (dx == 1 and tx + 1 - fx > reach):
        continue
      for dy in (-1, 0, 1):
        if (dy == -1 and fy - ty > reach) or (dy == 1 and ty + 1 - fy > reach):
          continue
        for road in self._roads(tx + dx, ty + dy):
          pts = (road.points + (tx + dx - fx, ty + dy - fy)) * tile_m  # meters from the fix, x east, y south
          p0, d = pts[:-1], np.diff(pts, axis=0)
          length2 = np.maximum((d * d).sum(axis=1), 1e-9)
          t = np.clip(-(p0 * d).sum(axis=1) / length2, 0.0, 1.0)
          dist = np.hypot(p0[:, 0] + t * d[:, 0], p0[:, 1] + t * d[:, 1])
          i = int(np.argmin(dist))
          if dist[i] > MAX_DISTANCE:
            continue
          direction = math.degrees(math.atan2(d[i, 0], -d[i, 1])) % 360.0
          error = angle_diff(direction, bearing)
          if not road.oneway:
            error = min(error, angle_diff(direction + 180.0, bearing))
          if error > MAX_HEADING_ERROR:
            continue
          score = dist[i] + HEADING_WEIGHT * error
          if score < best_score:
            best_score = score
            best = RoadMatch(road.kind, road.detail, road.oneway, road.link, float(dist[i]), error)
    return best
