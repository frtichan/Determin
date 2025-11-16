from sqlmodel import SQLModel, create_engine

from .config import get_settings, ensure_data_dir


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        ensure_data_dir()
        db_url = get_settings().db_url
        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        _engine = create_engine(db_url, echo=False, connect_args=connect_args)
    return _engine


def init_db() -> None:
    # Import models to register metadata
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


