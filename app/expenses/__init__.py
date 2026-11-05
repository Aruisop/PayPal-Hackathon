"""Informal personal expense splitting: never PayPal-authoritative money.

These are IOU-style notes between named people (friends or group members),
confirmed manually by the person who fronted the cost. They cannot grant
inventory, tickets, or any PayPal payment state, and they never run inside a
database transaction together with a network call.
"""
