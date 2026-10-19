"""Compatibility module for the relocated application service."""

import sys
from app.payments import paypal as _paypal
sys.modules[__name__] = _paypal
