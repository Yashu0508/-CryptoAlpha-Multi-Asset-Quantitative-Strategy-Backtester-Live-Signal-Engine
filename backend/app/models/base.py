"""Declarative model base shared by all ORM entities."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for database models."""

