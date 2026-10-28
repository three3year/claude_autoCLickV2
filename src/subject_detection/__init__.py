__all__ = ["Engine", "QueryResult", "Library", "make_library"]


def __getattr__(name):
    if name in ("Engine", "QueryResult"):
        from . import engine
        return getattr(engine, name)
    if name in ("Library", "make_library"):
        from . import library
        return getattr(library, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
