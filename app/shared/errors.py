"""Shared domain errors that do not depend on Flask or service implementations."""


class BookingError(Exception):
    """A safe, public collaborative-booking failure."""

    def __init__(self, issue, status=409):
        self.issue, self.status = issue, status
        super().__init__(issue)
