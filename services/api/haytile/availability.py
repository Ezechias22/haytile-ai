"""Operator service switches, checked before admitting expensive work."""

import os


def generation_enabled():
    return os.environ.get("HAYTILE_GENERATION_ENABLED", "1") == "1"


def worker_enabled():
    return os.environ.get("HAYTILE_WORKER_ENABLED", "1") == "1"
