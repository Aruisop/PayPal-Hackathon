"""Compatibility module for the relocated application service."""

import sys
from app.recommendations import semantic as _semantic
sys.modules[__name__] = _semantic
