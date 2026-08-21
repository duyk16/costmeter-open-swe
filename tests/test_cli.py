import json
from urllib.error import HTTPError

from costmeter import cli


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def read(self):
        return json.dumps(self.body).encode("utf-8")


def test_event_posts_payload_and_prints_response(monkeypatch, capsys):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse({"id": 1, "team": "platform"})

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    exit_code = cli.main(
        [
            "--base-url",
            "http://costmeter.local/api",
            "event",
            "--team",
            "platform",
            "--model",
            "gpt-4.1-mini",
            "--input-tokens",
            "100",
            "--output-tokens",
            "25",
            "--cost-usd",
            "0.12",
        ]
    )

    request, timeout = requests[0]
    assert exit_code == 0
    assert timeout == cli.DEFAULT_TIMEOUT_SECONDS
    assert request.full_url == "http://costmeter.local/api/events"
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    assert json.loads(request.data.decode("utf-8")) == {
        "team": "platform",
        "model": "gpt-4.1-mini",
        "input_tokens": 100,
        "output_tokens": 25,
        "cost_usd": 0.12,
    }
    assert json.loads(capsys.readouterr().out) == {"id": 1, "team": "platform"}


def test_report_fetches_team_report(monkeypatch, capsys):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return FakeResponse({"team": "platform", "event_count": 2})

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    exit_code = cli.main(
        [
            "--base-url",
            "http://costmeter.local",
            "report",
            "--team",
            "platform tools",
        ]
    )

    assert exit_code == 0
    assert requests[0].full_url == "http://costmeter.local/report?team=platform+tools"
    assert requests[0].get_method() == "GET"
    assert json.loads(capsys.readouterr().out) == {
        "team": "platform",
        "event_count": 2,
    }


def test_daily_report_uses_daily_endpoint(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return FakeResponse([{"date": "2025-01-01", "cost_usd": 1.23}])

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    exit_code = cli.main(
        [
            "--base-url",
            "http://costmeter.local/",
            "report",
            "--daily",
            "--team",
            "platform",
        ]
    )

    assert exit_code == 0
    assert requests[0].full_url == "http://costmeter.local/report/daily?team=platform"


def test_http_error_returns_nonzero(monkeypatch, capsys):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            422,
            "Unprocessable Entity",
            hdrs=None,
            fp=FakeResponse({"detail": "invalid"}),
        )

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    exit_code = cli.main(
        ["--base-url", "http://costmeter.local", "report", "--team", "platform"]
    )

    assert exit_code == 1
    assert "HTTP 422" in capsys.readouterr().err
