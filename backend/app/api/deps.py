from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from app.services.bus import Bus
from app.services.hub import SnapshotHub


def get_session(request: HTTPConnection) -> Iterator[Session]:
    yield from request.app.state.db.dependency()


def get_bus(request: HTTPConnection) -> Bus:
    return request.app.state.bus


def get_hub(request: HTTPConnection) -> SnapshotHub:
    return request.app.state.hub


SessionDep = Annotated[Session, Depends(get_session)]
BusDep = Annotated[Bus, Depends(get_bus)]
HubDep = Annotated[SnapshotHub, Depends(get_hub)]
