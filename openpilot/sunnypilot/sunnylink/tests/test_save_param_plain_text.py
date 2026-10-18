"""RehkopfPilot: sunnylink saveParams accepts a text setting sent as plain text instead of base64."""
import base64
import gzip

import pytest

from openpilot.common.params import ParamKeyType
from openpilot.sunnypilot.sunnylink.utils import _decode_param_value

b64 = lambda b: base64.b64encode(b).decode()


def test_base64_values_unchanged():
  assert _decode_param_value(b64(b"All states (~6.0 GB)"), ParamKeyType.STRING, False) == b"All states (~6.0 GB)"
  assert _decode_param_value(b64(b"1"), ParamKeyType.BOOL, False) == b"1"
  assert _decode_param_value(b64(gzip.compress(b"US")), ParamKeyType.STRING, True) == b"US"
  assert _decode_param_value(b64(b"\xad\x00"), ParamKeyType.BYTES, False) == b"\xad\x00"


def test_plain_text_string_is_kept_as_text():
  # exact payload from the van's swaglog, 2026-10-16
  assert _decode_param_value("United States", ParamKeyType.STRING, False) == b"United States"


def test_garbage_for_non_string_types_still_raises():
  with pytest.raises(Exception):
    _decode_param_value("not base64!", ParamKeyType.BOOL, False)
