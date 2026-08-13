#!/usr/bin/env python3
"""Terminal UI for polling configured GET APIs and showing NAME/VALUE.

Reads a JSON config (list of API definitions), calls each endpoint,
extracts a value via a dot-path expression and renders results as an
ASCII table. Supports a curses-based interactive TUI (refresh with
`r`, quit with `q`) and a `--once` mode that prints the table once
and exits (useful for scripting and tests).

Built-in default config includes a DeepSeek balance example using the
`DEEPSEEK_API_KEY` environment variable against
https://api.deepseek.com/user/balance, extracting
`balance_infos[].total_balance`.
"""

from __future__ import annotations

import argparse
import curses
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional


DEFAULT_CONFIG: list[dict[str, Any]] = [
    {
        "name": "DeepSeek",
        "url": "https://api.deepseek.com/user/balance",
        "env_var": "DEEPSEEK_API_KEY",
        "auth": "bearer",
        "value_path": "balance_infos[0].total_balance",
    }
]


@dataclass
class ApiConfig:
    """Configuration for a single API endpoint.

    Attributes:
        name: Display name shown in the NAME column.
        url: Full GET URL to call.
        env_var: Name of an environment variable holding a secret
            (e.g. an API key). Optional.
        headers: Extra static headers to send with the request.
        value_path: Dot path expression used to extract the display
            value from the parsed JSON response body. Supports list
            indexing and `[]` to mean "first element" of a list, e.g.
            `balance_infos[].total_balance` or
            `balance_infos[0].total_balance`.
        auth: If set to "bearer", the value of `env_var` is sent as
            an `Authorization: Bearer <value>` header.
    """

    name: str
    url: str
    env_var: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    value_path: str = ""
    auth: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApiConfig":
        """Build an ApiConfig from a plain dict (parsed JSON entry).

        Args:
            data: Mapping with keys name, url, env_var, headers,
                value_path, auth.

        Returns:
            A populated ApiConfig instance.

        Raises:
            ValueError: If required keys `name` or `url` are missing.
        """
        if "name" not in data or "url" not in data:
            raise ValueError("config entry requires 'name' and 'url'")
        return cls(
            name=str(data["name"]),
            url=str(data["url"]),
            env_var=data.get("env_var"),
            headers=dict(data.get("headers") or {}),
            value_path=str(data.get("value_path", "")),
            auth=data.get("auth"),
        )


def load_config(path: Optional[str]) -> list[ApiConfig]:
    """Load API configs from a JSON file, or fall back to defaults.

    Args:
        path: Path to a JSON file containing a list of API config
            objects. If None, the built-in DEFAULT_CONFIG is used.

    Returns:
        List of parsed ApiConfig objects.

    Raises:
        ValueError: If the file content is not a JSON list, or an
            entry is malformed.
        OSError: If the file cannot be read.
    """
    if path is None:
        raw = DEFAULT_CONFIG
    else:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, list):
            raise ValueError("config file must contain a JSON list")
    return [ApiConfig.from_dict(entry) for entry in raw]


def _parse_path_token(token: str) -> tuple[str, list[Optional[int]]]:
    """Parse a single dot-path token into a key and index list.

    Handles tokens like `balance_infos`, `balance_infos[0]`, or
    `balance_infos[]` (empty brackets mean "first element").

    Args:
        token: A single path segment, possibly with bracket indices.

    Returns:
        Tuple of (key, indices) where indices is a list of ints (or
        None for an empty `[]` meaning "take first element").
    """
    key = token
    indices: list[Optional[int]] = []
    while key.endswith("]") and "[" in key:
        open_pos = key.rindex("[")
        idx_str = key[open_pos + 1 : -1]
        indices.insert(0, int(idx_str) if idx_str else None)
        key = key[:open_pos]
    return key, indices


def extract_value(data: Any, path: str) -> Any:
    """Extract a value from parsed JSON using a dot-path expression.

    Supports dict key access and list indexing, including empty
    brackets `[]` meaning "first element of the list".

    Args:
        data: Parsed JSON structure (dict/list/scalar).
        path: Dot-separated path expression, e.g.
            `balance_infos[0].total_balance` or
            `balance_infos[].total_balance`.

    Returns:
        The extracted value.

    Raises:
        KeyError: If a dict key in the path is missing.
        IndexError: If a list index is out of range.
        TypeError: If path traversal hits an incompatible type.
        ValueError: If path is empty.
    """
    if not path:
        raise ValueError("value_path must not be empty")
    current: Any = data
    for token in path.split("."):
        key, indices = _parse_path_token(token)
        if key:
            if not isinstance(current, dict):
                raise TypeError(f"expected dict to access key '{key}'")
            if key not in current:
                raise KeyError(key)
            current = current[key]
        for idx in indices:
            if not isinstance(current, list):
                raise TypeError("expected list for index access")
            if not current:
                raise IndexError("list is empty")
            use_idx = 0 if idx is None else idx
            current = current[use_idx]
    return current


class ApiError(Exception):
    """Raised when fetching or parsing an API result fails."""


def fetch_value(config: ApiConfig, timeout: float = 10.0) -> str:
    """Call the configured API and return the extracted value as text.

    Args:
        config: The API configuration to call.
        timeout: Request timeout in seconds.

    Returns:
        String representation of the extracted value.

    Raises:
        ApiError: If the request fails, the response is not valid
            JSON, or the value cannot be extracted.
    """
    headers = dict(config.headers)
    secret: Optional[str] = None
    if config.env_var:
        secret = os.environ.get(config.env_var)
        if secret is None:
            raise ApiError(f"env var '{config.env_var}' is not set")
        if config.auth == "bearer":
            headers["Authorization"] = f"Bearer {secret}"

    request = urllib.request.Request(config.url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise ApiError(f"HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"request failed: {exc.reason}") from exc
    except OSError as exc:
        raise ApiError(f"request failed: {exc}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ApiError(f"invalid JSON response: {exc}") from exc

    try:
        value = extract_value(parsed, config.value_path)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ApiError(f"value_path error: {exc}") from exc

    return str(value)


@dataclass
class Row:
    """A single result row for the table.

    Attributes:
        name: API name.
        value: Extracted value, or an error message string.
        is_error: Whether `value` represents an error rather than
            a successful result.
    """

    name: str
    value: str
    is_error: bool = False


def poll_all(configs: list[ApiConfig]) -> list[Row]:
    """Fetch values for all configs, capturing per-row errors.

    Args:
        configs: List of API configs to poll.

    Returns:
        List of Row results, one per config, in the same order.
    """
    rows: list[Row] = []
    for cfg in configs:
        try:
            value = fetch_value(cfg)
            rows.append(Row(name=cfg.name, value=value, is_error=False))
        except ApiError as exc:
            rows.append(Row(name=cfg.name, value=f"ERROR: {exc}", is_error=True))
    return rows


def render_table(rows: list[Row]) -> str:
    """Render rows as an ASCII table with NAME/VALUE columns.

    Args:
        rows: Result rows to display.

    Returns:
        Multi-line string containing the formatted table.
    """
    name_header, value_header = "NAME", "VALUE"
    name_width = max([len(name_header)] + [len(r.name) for r in rows])
    value_width = max([len(value_header)] + [len(r.value) for r in rows])

    def sep(left: str, mid: str, right: str) -> str:
        return left + mid.join("-" * (name_width + 2)
                                for _ in range(1)) + mid + mid.join(
            "-" * (value_width + 2) for _ in range(1)) + right

    top = "+" + "-" * (name_width + 2) + "+" + "-" * (value_width + 2) + "+"
    header = (
        "| " + name_header.ljust(name_width) + " | "
        + value_header.ljust(value_width) + " |"
    )
    lines = [top, header, top]
    for row in rows:
        lines.append(
            "| " + row.name.ljust(name_width) + " | "
            + row.value.ljust(value_width) + " |"
        )
    lines.append(top)
    return "\n".join(lines)


def run_once(configs: list[ApiConfig]) -> str:
    """Poll once and return the rendered table (no curses).

    Args:
        configs: API configs to poll.

    Returns:
        Rendered ASCII table string.
    """
    rows = poll_all(configs)
    return render_table(rows)


def run_tui(stdscr: Any, configs: list[ApiConfig]) -> None:
    """Run the interactive curses TUI loop.

    Displays the table and waits for input: `r` refreshes the data,
    `q` quits the application.

    Args:
        stdscr: curses standard screen window.
        configs: API configs to poll and display.
    """
    curses.curs_set(0)
    stdscr.nodelay(False)
    rows = poll_all(configs)

    while True:
        stdscr.erase()
        table = render_table(rows)
        for i, line in enumerate(table.splitlines()):
            try:
                stdscr.addstr(i, 0, line)
            except curses.error:
                pass
        footer = "[r] refresh  [q] quit"
        try:
            stdscr.addstr(len(table.splitlines()) + 1, 0, footer)
        except curses.error:
            pass
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            break
        if key in (ord("r"), ord("R")):
            rows = poll_all(configs)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list to parse; defaults to sys.argv[1:].

    Returns:
        Parsed argparse.Namespace with `config` and `once` fields.
    """
    parser = argparse.ArgumentParser(
        description="Poll configured GET APIs and show NAME/VALUE table."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON config file (list of API definitions).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print the table once and exit, without curses TUI.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point.

    Args:
        argv: Optional argument list override (used for testing).

    Returns:
        Process exit code.
    """
    args = parse_args(argv)
    try:
        configs = load_config(args.config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    if args.once:
        print(run_once(configs))
        return 0

    try:
        curses.wrapper(run_tui, configs)
    except curses.error as exc:
        print(f"TUI error (try --once): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
