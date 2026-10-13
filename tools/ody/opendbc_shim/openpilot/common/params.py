# Test-only stand-in for openpilot.common.params, so opendbc's own test suite runs outside openpilot
# (sunnypilot/MVL's Honda controller imports it on the device).
class Params:
  _store: dict = {}

  def get(self, key, *a, **k):
    return self._store.get(key)

  def get_bool(self, key, *a, **k):
    return bool(self._store.get(key, False))

  def put(self, key, value, *a, **k):
    self._store[key] = value

  def put_bool(self, key, value, *a, **k):
    self._store[key] = bool(value)

  def put_nonblocking(self, key, value, *a, **k):
    self._store[key] = value
