"""Public collaborative-booking errors, shared without service import cycles."""


class BookingError(Exception):
    def __init__(self, issue, status=409):
        self.issue, self.status = issue, status
        super().__init__(issue)
