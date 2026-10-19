"""Compatibility alias for the relocated planning service."""
import sys

from app.planning import service as _service

# Preserve module-level patch points used by existing integrations and tests.
sys.modules[__name__] = _service
