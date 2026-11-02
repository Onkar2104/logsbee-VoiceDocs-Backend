"""Backward-compatible database exports.

The canonical database setup lives in app.db.session.
"""
from app.db.session import Base, SessionLocal, engine, get_db

__all__ = ["Base", "SessionLocal", "engine", "get_db"]
