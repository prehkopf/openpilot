"""RehkopfPilot pass hints: which road the van is on, and whether it is one carriageway of a divided road."""
import math

from openpilot.selfdrive.navigation.road_match import RoadMatcher, ZOOM, tile_coords
from openpilot.selfdrive.navigation.vector_tile import decode_roads

X, Y = 8675, 13084  # a z15 tile in Georgia


def varint(value):
  out = bytearray()
  while value > 127:
    out.append((value & 127) | 128)
    value >>= 7
  out.append(value)
  return bytes(out)


def field(number, value):
  if isinstance(value, bytes):
    return varint(number << 3 | 2) + varint(len(value)) + value
  return varint(number << 3) + varint(value)


def zigzag(v):
  return (v << 1) ^ (v >> 31)


def tile(*roads):
  """roads: (x0, y0, x1, y1, properties) in tile units (0..4096, y down). A line drawn from (x0, y0) to (x1, y1)."""
  keys, values, features = [], [], b''
  for x0, y0, x1, y1, props in roads:
    tags = []
    for k, v in props.items():
      if k not in keys:
        keys.append(k)
      if v not in values:
        values.append(v)
      tags += [keys.index(k), values.index(v)]
    geometry = b''.join(varint(c) for c in [9, zigzag(x0), zigzag(y0), 10, zigzag(x1 - x0), zigzag(y1 - y0)])
    features += field(2, field(2, b''.join(varint(t) for t in tags)) + field(3, 2) + field(4, geometry))
  layer = field(15, 2) + field(1, b'roads') + features
  layer += b''.join(field(3, k.encode()) for k in keys)
  layer += b''.join(field(4, field(7, 1) if v is True else field(1, v.encode())) for v in values)
  layer += field(5, 4096)
  return field(3, layer)


class Archive:
  def __init__(self, tiles):
    self.tiles = tiles

  def get(self, z, x, y):
    assert z == ZOOM
    return self.tiles.get((x, y))


def latlon(fx, fy):
  n = 2 ** ZOOM
  return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * fy / n)))), fx / n * 360.0 - 180.0


def tile_m():
  lat, _ = latlon(X + 0.5, Y + 0.5)
  return 40075016.686 * math.cos(math.radians(lat)) / 2 ** ZOOM


SOUTHBOUND_ONEWAY = (2048, 0, 2048, 4096, {'kind': 'highway', 'kind_detail': 'motorway', 'oneway': 'yes'})
TWO_WAY = (2048, 0, 2048, 4096, {'kind': 'major_road', 'kind_detail': 'secondary', 'oneway': 'no'})
RAMP = (2048, 0, 2048, 4096, {'kind': 'highway', 'kind_detail': 'motorway_link', 'oneway': 'yes', 'is_link': True})


def match(road, east_m=0.0, bearing=180.0):
  fx = X + 0.5 + east_m / tile_m()
  return RoadMatcher(Archive({(X, Y): tile(road)})).match(*latlon(fx, Y + 0.5), bearing)


def test_decoder_keeps_oneway_and_ramp():
  oneway, ramp, two_way = (decode_roads(tile(r))[0] for r in (SOUTHBOUND_ONEWAY, RAMP, TWO_WAY))
  assert oneway.oneway and not oneway.link and oneway.detail == 'motorway'
  assert ramp.oneway and ramp.link
  assert not two_way.oneway


def test_oneway_matches_only_in_its_direction_of_travel():
  m = match(SOUTHBOUND_ONEWAY, bearing=180.0)
  assert m is not None and m.oneway and m.kind == 'highway' and m.heading_error < 1.0
  # northbound a few meters off is the other carriageway: never this one
  assert match(SOUTHBOUND_ONEWAY, bearing=0.0) is None


def test_two_way_matches_both_directions():
  assert match(TWO_WAY, bearing=0.0) is not None and match(TWO_WAY, bearing=180.0) is not None
  assert not match(TWO_WAY).oneway


def test_distance_and_heading_limits():
  assert match(SOUTHBOUND_ONEWAY, east_m=12.0) is not None
  assert match(SOUTHBOUND_ONEWAY, east_m=30.0) is None
  assert match(SOUTHBOUND_ONEWAY, bearing=180.0 + 30.0) is not None
  assert match(SOUTHBOUND_ONEWAY, bearing=180.0 + 50.0) is None


def test_closest_road_wins_and_off_the_map_is_none():
  near = (2100, 0, 2100, 4096, {'kind': 'major_road', 'kind_detail': 'primary', 'oneway': 'yes'})
  far = (2400, 0, 2400, 4096, {'kind': 'highway', 'kind_detail': 'motorway', 'oneway': 'yes'})
  m = RoadMatcher(Archive({(X, Y): tile(far, near)})).match(*latlon(X + 2090 / 4096, Y + 0.5), 180.0)
  assert m is not None and m.detail == 'primary'
  assert RoadMatcher(Archive({})).match(*latlon(X + 0.5, Y + 0.5), 180.0) is None


def test_road_in_the_neighboring_tile():
  # the van is 5 m inside the tile's east edge; the road runs 5 m into the next tile
  edge_road = (int(5 / tile_m() * 4096), 0, int(5 / tile_m() * 4096), 4096, SOUTHBOUND_ONEWAY[4])
  fx = X + 1 - 5 / tile_m()
  m = RoadMatcher(Archive({(X + 1, Y): tile(edge_road)})).match(*latlon(fx, Y + 0.5), 180.0)
  assert m is not None and 8.0 < m.distance < 12.0


def test_tile_coords_round_trip():
  lat, lon = latlon(X + 0.25, Y + 0.75)
  fx, fy = tile_coords(lat, lon)
  assert abs(fx - (X + 0.25)) < 1e-6 and abs(fy - (Y + 0.75)) < 1e-6
