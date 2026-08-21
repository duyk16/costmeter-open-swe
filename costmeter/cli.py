import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SECONDS = 30


def _json_request(
    method: str,
    base_url: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if query:
        url = f"{url}?{urlencode(query)}"

    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")

    if not body:
        return None
    return json.loads(body)


def post_event(args: argparse.Namespace) -> Any:
    return _json_request(
        "POST",
        args.base_url,
        "/events",
        payload={
            "team": args.team,
            "model": args.model,
            "input_tokens": args.input_tokens,
            "output_tokens": args.output_tokens,
            "cost_usd": args.cost_usd,
        },
    )


def get_report(args: argparse.Namespace) -> Any:
    path = "/report/daily" if args.daily else "/report"
    query = {"team": args.team} if args.team else None
    return _json_request("GET", args.base_url, path, query=query)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="costmeter", description="Send events to and read reports from costmeter."
    )
    parser.add_argument("--base-url", required=True, help="Base URL for the costmeter service")

    subparsers = parser.add_subparsers(dest="command", required=True)

    event_parser = subparsers.add_parser("event", help="Post a usage event")
    event_parser.add_argument("--team", required=True)
    event_parser.add_argument("--model", required=True)
    event_parser.add_argument("--input-tokens", required=True, type=int)
    event_parser.add_argument("--output-tokens", required=True, type=int)
    event_parser.add_argument("--cost-usd", required=True, type=float)
    event_parser.set_defaults(handler=post_event)

    report_parser = subparsers.add_parser("report", help="Print a cost report")
    report_parser.add_argument("--team", help="Team to report on")
    report_parser.add_argument(
        "--daily", action="store_true", help="Use the /report/daily endpoint"
    )
    report_parser.set_defaults(handler=get_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = args.handler(args)
    except HTTPError as error:
        body = error.read().decode("utf-8")
        print(f"HTTP {error.code}: {body or error.reason}", file=sys.stderr)
        return 1
    except URLError as error:
        print(f"Request failed: {error.reason}", file=sys.stderr)
        return 1

    if result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
