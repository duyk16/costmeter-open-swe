import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    team: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost: float = Field(ge=0)
    currency: str = Field(min_length=1)


class Event(EventCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class Report(BaseModel):
    team: str
    event_count: int
    input_tokens: int
    output_tokens: int
    cost: float
    currency: str


class DailyReport(Report):
    date: date


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
                cost REAL NOT NULL,
                currency TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(events)")}
        if "cost" not in columns and "cost_usd" in columns:
            connection.execute("ALTER TABLE events RENAME COLUMN cost_usd TO cost")
            columns.remove("cost_usd")
            columns.add("cost")
        if "currency" not in columns:
            connection.execute("ALTER TABLE events ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'")
        if "created_at" not in columns:
            connection.execute("ALTER TABLE events ADD COLUMN created_at TEXT")
            connection.execute("UPDATE events SET created_at = CURRENT_TIMESTAMP")
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
            INSERT INTO events (
                team, model, input_tokens, output_tokens, cost, currency, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                event.team,
                event.model,
                event.input_tokens,
                event.output_tokens,
                event.cost,
                event.currency,
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
                COALESCE(SUM(cost), 0.0) AS cost,
                COALESCE(MAX(currency), 'USD') AS currency
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
            "cost": row["cost"],
            "currency": row["currency"],
        }

    @app.get("/report/daily", response_model=list[DailyReport])
    def get_daily_report(
        team: Annotated[str, Query(min_length=1)],
        from_date: Annotated[date, Query(alias="from")],
        to_date: Annotated[date, Query(alias="to")],
        connection: Database,
    ) -> list[dict]:
        if from_date > to_date:
            raise HTTPException(status_code=400, detail="from must be on or before to")

        rows = connection.execute(
            """
            SELECT
                date(created_at) AS report_date,
                COUNT(*) AS event_count,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(cost), 0.0) AS cost,
                COALESCE(MAX(currency), 'USD') AS currency
            FROM events
            WHERE team = ? AND date(created_at) BETWEEN ? AND ?
            GROUP BY report_date
            """,
            (team, from_date.isoformat(), to_date.isoformat()),
        ).fetchall()
        totals_by_date = {date.fromisoformat(row["report_date"]): row for row in rows}

        report = []
        current_date = from_date
        while current_date <= to_date:
            row = totals_by_date.get(current_date)
            report.append(
                {
                    "date": current_date,
                    "team": team,
                    "event_count": row["event_count"] if row else 0,
                    "input_tokens": row["input_tokens"] if row else 0,
                    "output_tokens": row["output_tokens"] if row else 0,
                    "cost": row["cost"] if row else 0.0,
                    "currency": row["currency"] if row else "USD",
                }
            )
            current_date += timedelta(days=1)
        return report

    return app


app = create_app()
