"""Reusable FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from ..db.session import get_session

SessionDep = Annotated[Session, Depends(get_session)]
