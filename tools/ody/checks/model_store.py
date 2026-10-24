#!/usr/bin/env python3
# Prepush check: can this build load the models people pick in the model store? The default model is compiled on the
# device at install time, so it always matches; store models are downloaded precompiled. Fayette shipped with a tinygrad
# pin that broke every v23 store model (TSFDOM wouldn't calibrate) and no test noticed.
# Checks the live catalog this build reads: its bundles must use this build's selector version, and the head of one
# store artifact (an HTTP range, 64 KB) must be a plain artifact this build's loader can read.
# usage: model_store.py   (network; prints WARN instead of failing when offline)
import json
import struct
import sys
import urllib.request

from openpilot.sunnypilot.modeld_v2.helpers import MAGIC
from openpilot.sunnypilot.models.fetcher import ModelFetcher
from openpilot.sunnypilot.models.helpers import REQUIRED_JSON_VERSION

SAMPLE = "TSFDOM"
HEAD_BYTES = 64 * 1024


def main() -> int:
  try:
    catalog = json.load(urllib.request.urlopen(ModelFetcher.MODEL_URL, timeout=30))
  except OSError as e:
    print(f"WARN model catalog unreachable ({type(e).__name__}), store models not checked")
    return 0
  bundles = catalog["bundles"]
  usable = [b for b in bundles if int(b["minimum_selector_version"]) == REQUIRED_JSON_VERSION]
  print(f"{ModelFetcher.MODEL_URL.rsplit('/', 1)[1]}: {len(usable)}/{len(bundles)} bundles at selector " +
        f"{REQUIRED_JSON_VERSION}, catalog tinygrad_ref {catalog.get('tinygrad_ref', '?')[:9]}")
  if not usable:
    print("FAIL no store model in the catalog matches this build's selector version")
    return 1

  bundle = next((b for b in usable if b["short_name"] == SAMPLE), usable[0])
  url = bundle["models"][0]["artifact"]["download_uri"]["url"]
  try:
    head = urllib.request.urlopen(urllib.request.Request(url, headers={"Range": f"bytes=0-{HEAD_BYTES - 1}"}), timeout=60).read()
  except OSError as e:
    print(f"WARN {bundle['short_name']} artifact unreachable ({type(e).__name__})")
    return 0
  if head[:len(MAGIC)] != MAGIC:
    print(f"FAIL {bundle['short_name']} is not a plain artifact (starts {head[:8]!r}); this build's loader can't read it")
    return 1
  size = struct.unpack_from("<Q", head, len(MAGIC))[0]
  if len(MAGIC) + 8 + size <= len(head):
    header = json.loads(head[len(MAGIC) + 8:len(MAGIC) + 8 + size])
    print(f"{bundle['short_name']}: plain artifact, {len(header['parts'])} parts")
  else:
    print(f"{bundle['short_name']}: plain artifact (header larger than the sampled {HEAD_BYTES} bytes)")
  print("OK")
  return 0


if __name__ == "__main__":
  sys.exit(main())
