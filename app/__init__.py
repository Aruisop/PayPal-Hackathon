"""Application package and factory entry point."""


def create_app(*args, **kwargs):
    """Load the Flask factory lazily so domain modules can be imported safely."""
    from .factory import create_app as factory
    return factory(*args, **kwargs)


__all__ = ["create_app"]
