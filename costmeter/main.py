import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    team: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class Event(EventCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class Report(BaseModel):
    team: str
    event_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


def initialize_database(db_path: str) -> None:
    path = Path(db_path)
    if path.parent != Path(""):
        path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL
            )
            """
        )
        connection.commit()


def create_app(db_path: str | None = None) -> FastAPI:
    database_path = db_path or os.getenv("COSTMETER_DB_PATH", "costmeter.db")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(database_path)
        yield

    app = FastAPI(title="costmeter", lifespan=lifespan)
    app.state.db_path = database_path

    def get_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(app.state.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    Database = Annotated[sqlite3.Connection, Depends(get_connection)]

    @app.post("/events", response_model=Event, status_code=201)
    def create_event(event: EventCreate, connection: Database) -> dict:
        cursor = connection.execute(
            """
            INSERT INTO events (team, model, input_tokens, output_tokens, cost_usd)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.team,
                event.model,
                event.input_tokens,
                event.output_tokens,
                event.cost_usd,
            ),
        )
        connection.commit()
        return {"id": cursor.lastrowid, **event.model_dump()}

    @app.get("/report", response_model=Report)
    def get_report(
        team: Annotated[str, Query(min_length=1)], connection: Database
    ) -> dict:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS event_count,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(cost_usd), 0.0) AS cost_usd
            FROM events
            WHERE team = ?
            """,
            (team,),
        ).fetchone()
        return {
            "team": team,
            "event_count": row["event_count"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cost_usd": row["cost_usd"],
        }

    return app


app = create_app()
