"""RehkopfPilot navigation without prime: offline map file, personal Mapbox token, no secrets or places in logs."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

from openpilot.selfdrive.navigation.pmtiles import PMTiles
from openpilot.selfdrive.navigation.tests.test_navigation import make_archive, road_tile, route_engine
from openpilot.selfdrive.navigation.tiles import LocalTiles, open_tiles
from openpilot.selfdrive.ui.sunnypilot.mici.widgets.destination import NONE, DestinationToggle, favorites, selected

TOKEN = 'pk.secret-test-token'
HOME = {"name": "home", "latitude": 34.05, "longitude": -84.68}
SCHOOL = {"name": "school", "latitude": 34.09, "longitude": -84.60}


class FakeParams:
  def __init__(self, **values):
    self.values = dict(values)

  def get(self, key, *a, **kw):
    return self.values.get(key)

  def put(self, key, value):
    self.values[key] = value

  def put_bool(self, key, value):
    self.values[key] = value

  def remove(self, key):
    self.values.pop(key, None)


class TestLocalTiles(unittest.TestCase):
  def test_reads_a_local_archive_like_the_remote_one(self):
    with tempfile.TemporaryDirectory() as d:
      path = Path(d) / 'map.pmtiles'
      path.write_bytes(make_archive())
      with closing(PMTiles(LocalTiles(path))) as archive:
        self.assertEqual(archive.get(0, 0, 0), road_tile())
        archive.prefetch([(0, 0, 0)])  # nothing to fetch, must not fail

  def test_open_tiles_prefers_the_local_file(self):
    with tempfile.TemporaryDirectory() as d:
      path = Path(d) / 'map.pmtiles'
      with patch('openpilot.selfdrive.navigation.tiles.RemoteTiles') as remote:
        self.assertIs(open_tiles(path), remote.return_value)  # no file yet: the hosted archive
        path.write_bytes(make_archive())
        source = open_tiles(path)
        self.assertIsInstance(source, LocalTiles)
        source.close()
        source.close()  # closing twice is harmless


class TestMapboxToken(unittest.TestCase):
  def test_token_param_routes_straight_to_mapbox(self):
    engine = route_engine(MagicMock(), MagicMock(), {'MapboxToken': TOKEN})
    self.assertEqual(engine.mapbox_token, TOKEN)
    self.assertEqual(engine.mapbox_host, 'https://api.mapbox.com')
    self.assertIsNone(engine.api)

  def test_no_token_keeps_the_comma_proxy(self):
    engine = route_engine(MagicMock(), MagicMock(), {})
    self.assertIsNone(engine.mapbox_token)
    self.assertIn('/v1/nav', engine.mapbox_host)

  def test_failed_request_logs_neither_token_nor_places(self):
    engine = route_engine(MagicMock(), MagicMock(), {'MapboxToken': TOKEN})
    engine.last_position = (-84.68, 34.05)
    logged = []
    log = SimpleNamespace(**{name: (lambda *a, **kw: logged.append(repr((a, kw)))) for name in ('warning', 'exception', 'event', 'error')})
    leaky = requests.exceptions.ConnectionError(f"HTTPSConnectionPool url: /directions/v5?access_token={TOKEN}")
    with patch('openpilot.selfdrive.navigation.navd.cloudlog', log), \
         patch('openpilot.selfdrive.navigation.navd.requests.get', side_effect=leaky):
      engine.calculate_route((-84.60, 34.09))
    self.assertTrue(logged)
    for line in logged:
      self.assertNotIn(TOKEN, line)
      self.assertNotIn('34.05', line)
      self.assertNotIn('34.09', line)
    self.assertIsNone(engine.route)


class TestDestination(unittest.TestCase):
  def test_favorites_skip_malformed_places(self):
    p = FakeParams(NavFavorites=[HOME, {"name": "x"}, {"name": NONE, "latitude": 1, "longitude": 1},
                                 {"name": "far", "latitude": 99, "longitude": 0}, SCHOOL, "junk"])
    self.assertEqual([f["name"] for f in favorites(p)], ["home", "school"])
    self.assertEqual(favorites(FakeParams()), [])
    self.assertEqual(favorites(FakeParams(NavFavorites={"name": "home"})), [])

  def test_selected_matches_the_current_destination(self):
    places = favorites(FakeParams(NavFavorites=[HOME, SCHOOL]))
    self.assertEqual(selected(FakeParams(NavDestination={"latitude": 34.09, "longitude": -84.60}), places), "school")
    self.assertEqual(selected(FakeParams(NavDestination={"latitude": 1.0, "longitude": 1.0}), places), NONE)
    self.assertEqual(selected(FakeParams(), places), NONE)

  def test_picking_a_place_sets_the_route_and_none_clears_it(self):
    params = FakeParams(NavFavorites=[HOME, SCHOOL], NavigationEnabled=False)
    toggle = SimpleNamespace(_params=params, _places=favorites(params))
    DestinationToggle._on_select(toggle, "school")
    self.assertEqual(params.values["NavDestination"], {"latitude": 34.09, "longitude": -84.60})
    self.assertTrue(params.values["NavigationEnabled"])
    DestinationToggle._on_select(toggle, NONE)
    self.assertNotIn("NavDestination", params.values)


if __name__ == "__main__":
  unittest.main()
