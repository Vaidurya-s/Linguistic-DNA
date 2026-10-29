from collections.abc import Iterator

from sqlalchemy import Connection

from app.db.session import engine


def get_conn() -> Iterator[Connection]:
    with engine.begin() as conn:
        yield conn
