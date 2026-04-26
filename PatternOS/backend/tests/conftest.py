"""Pytest hooks — keep optional imports stable across the suite."""

from app.compat.vectorbt_shim import apply_vectorbt_ptb_compat


def pytest_configure(config):  # noqa: ARG001
    apply_vectorbt_ptb_compat()
