import sqlite3

from fastapi.testclient import TestClient

from costmeter.main import create_app, initialize_database


def test_initialize_database_migrates_cost_and_currency_columns(tmp_path):
    db_path = tmp_path / "costmeter.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO events (
                team, model, input_tokens, output_tokens, cost_usd, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("platform", "gpt-4.1-mini", 100, 25, 0.12, "2025-01-01 09:00:00"),
        )

    initialize_database(str(db_path))

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(events)")}
        row = connection.execute("SELECT cost, currency FROM events").fetchone()

    assert "cost" in columns
    assert "cost_usd" not in columns
    assert row == (0.12, "USD")


def test_create_event_and_report_totals(tmp_path):
    app = create_app(str(tmp_path / "costmeter.db"))

    with TestClient(app) as client:
        first_response = client.post(
            "/events",
            json={
                "team": "platform",
                "model": "gpt-4.1-mini",
                "input_tokens": 100,
                "output_tokens": 25,
                "cost": 0.12,
                "currency": "USD",
            },
        )
        second_response = client.post(
            "/events",
            json={
                "team": "platform",
                "model": "gpt-4.1",
                "input_tokens": 300,
                "output_tokens": 50,
                "cost": 0.5,
                "currency": "USD",
            },
        )
        client.post(
            "/events",
            json={
                "team": "research",
                "model": "gpt-4.1-mini",
                "input_tokens": 999,
                "output_tokens": 999,
                "cost": 9.99,
                "currency": "USD",
            },
        )

        assert first_response.status_code == 201
        assert first_response.json() == {
            "id": 1,
            "team": "platform",
            "model": "gpt-4.1-mini",
            "input_tokens": 100,
            "output_tokens": 25,
            "cost": 0.12,
            "currency": "USD",
        }
        assert second_response.status_code == 201

        report_response = client.get("/report", params={"team": "platform"})

    assert report_response.status_code == 200
    assert report_response.json() == {
        "team": "platform",
        "event_count": 2,
        "input_tokens": 400,
        "output_tokens": 75,
        "cost": 0.62,
        "currency": "USD",
    }


def test_report_for_team_with_no_events_returns_zero_totals(tmp_path):
    app = create_app(str(tmp_path / "costmeter.db"))

    with TestClient(app) as client:
        response = client.get("/report", params={"team": "platform"})

    assert response.status_code == 200
    assert response.json() == {
        "team": "platform",
        "event_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost": 0.0,
        "currency": "USD",
    }


def test_daily_report_returns_totals_for_each_day_in_range(tmp_path):
    db_path = tmp_path / "costmeter.db"
    app = create_app(str(db_path))

    with TestClient(app) as client:
        with sqlite3.connect(db_path) as connection:
            connection.executemany(
                """
                INSERT INTO events (
                    team, model, input_tokens, output_tokens, cost, currency, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "platform",
                        "gpt-4.1-mini",
                        100,
                        25,
                        0.12,
                        "USD",
                        "2025-01-01 09:00:00",
                    ),
                    (
                        "platform",
                        "gpt-4.1",
                        300,
                        50,
                        0.5,
                        "USD",
                        "2025-01-01 13:00:00",
                    ),
                    (
                        "platform",
                        "gpt-4.1-mini",
                        50,
                        10,
                        0.07,
                        "USD",
                        "2025-01-03 10:00:00",
                    ),
                    (
                        "research",
                        "gpt-4.1-mini",
                        999,
                        999,
                        9.99,
                        "USD",
                        "2025-01-01 09:00:00",
                    ),
                    (
                        "platform",
                        "gpt-4.1-mini",
                        1,
                        1,
                        0.01,
                        "USD",
                        "2025-01-04 09:00:00",
                    ),
                ],
            )

        response = client.get(
            "/report/daily",
            params={"team": "platform", "from": "2025-01-01", "to": "2025-01-03"},
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "team": "platform",
            "event_count": 2,
            "input_tokens": 400,
            "output_tokens": 75,
            "cost": 0.62,
            "currency": "USD",
            "date": "2025-01-01",
        },
        {
            "team": "platform",
            "event_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0,
            "currency": "USD",
            "date": "2025-01-02",
        },
        {
            "team": "platform",
            "event_count": 1,
            "input_tokens": 50,
            "output_tokens": 10,
            "cost": 0.07,
            "currency": "USD",
            "date": "2025-01-03",
        },
    ]


def test_daily_report_rejects_invalid_date_range(tmp_path):
    app = create_app(str(tmp_path / "costmeter.db"))

    with TestClient(app) as client:
        response = client.get(
            "/report/daily",
            params={"team": "platform", "from": "2025-01-02", "to": "2025-01-01"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "from must be on or before to"}


def test_event_validation_rejects_invalid_payload(tmp_path):
    app = create_app(str(tmp_path / "costmeter.db"))

    with TestClient(app) as client:
        response = client.post(
            "/events",
            json={
                "team": "platform",
                "model": "gpt-4.1-mini",
                "input_tokens": -1,
                "output_tokens": 25,
                "cost": 0.12,
                "currency": "USD",
            },
        )

    assert response.status_code == 422
