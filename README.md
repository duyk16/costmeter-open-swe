# costmeter

A Python FastAPI service that records model usage events in SQLite and reports per-team totals.

## Requirements

- Python 3.11+

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Run the API

```bash
uvicorn costmeter.main:app --reload
```

## CLI

Post an event to a running costmeter service:

```bash
costmeter --base-url http://localhost:8000 event \
  --team platform \
  --model gpt-4.1-mini \
  --input-tokens 1000 \
  --output-tokens 250 \
  --cost-usd 0.42
```

Print a report:

```bash
costmeter --base-url http://localhost:8000 report --team platform
costmeter --base-url http://localhost:8000 report --daily --team platform
```

By default, events are stored in `costmeter.db`. Set `COSTMETER_DB_PATH` to use another SQLite file:

```bash
COSTMETER_DB_PATH=/tmp/costmeter.db uvicorn costmeter.main:app --reload
```

## Endpoints

### POST `/events`

Request body:

```json
{
  "team": "platform",
  "model": "gpt-4.1-mini",
  "input_tokens": 1000,
  "output_tokens": 250,
  "cost": 0.42,
  "currency": "USD"
}
```

Response body includes the stored event ID and submitted fields.

### GET `/report?team=<team>`

Returns totals for one team:

```json
{
  "team": "platform",
  "event_count": 1,
  "input_tokens": 1000,
  "output_tokens": 250,
  "cost": 0.42,
  "currency": "USD"
}
```

### GET `/report/daily?team=<team>&from=<date>&to=<date>`

Returns per-day totals for one team within the inclusive date range:

```json
[
  {
    "team": "platform",
    "event_count": 1,
    "input_tokens": 1000,
    "output_tokens": 250,
    "cost": 0.42,
    "currency": "USD",
    "date": "2025-01-01"
  }
]
```

## Test

```bash
make test
```
