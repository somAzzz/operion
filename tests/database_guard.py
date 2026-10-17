"""In-process capability issued only after the test runner creates its container."""

from contextlib import contextmanager

_owned_dsn: str | None = None


@contextmanager
def owned_database(dsn: str):
    global _owned_dsn
    if _owned_dsn is not None:
        raise RuntimeError("test database already owned")
    _owned_dsn = dsn
    try:
        yield
    finally:
        _owned_dsn = None


def require_owned_database(dsn: str) -> None:
    if not dsn or dsn != _owned_dsn:
        raise RuntimeError("Refusing destructive tests: use scripts/verify.sh postgres")
