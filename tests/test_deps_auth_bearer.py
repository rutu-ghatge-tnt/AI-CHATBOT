from __future__ import annotations

import pytest

from app.label_looker.core.deps_auth import _bearer, _merged_authorization_header
from app.label_looker.core.errors import ScannerApiError


def test_bearer_accepts_raw_jwt_without_prefix():
    tok = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    assert _bearer(tok) == tok


def test_bearer_strips_bearer_prefix():
    assert _bearer("Bearer   my-token  ") == "my-token"


def test_bearer_strips_double_bearer_prefix():
    assert _bearer("Bearer Bearer inner-token") == "inner-token"


def test_merged_header_normalizes_double_bearer_in_access_token_header():
    h = _merged_authorization_header(None, "Bearer eyJabc.def.ghi", None)
    assert h == "Bearer eyJabc.def.ghi"
    assert _bearer(h) == "eyJabc.def.ghi"


def test_bearer_rejects_empty():
    with pytest.raises(ScannerApiError) as ei:
        _bearer("")
    assert ei.value.status_code == 401
