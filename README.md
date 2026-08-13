# API Balances TUI

Simple standard-library-only Python TUI that polls configured GET
APIs and displays extracted values in a NAME/VALUE ASCII table.

## Requirements

- Python 3.9+ (standard library only: `urllib`, `json`, `curses`,
  `argparse`, `os`)
- `curses` is part of the standard library on Linux/macOS. On
  Windows, use `--once` mode or install `windows-curses`.

## Usage

Run with the built-in DeepSeek example (reads `DEEPSEEK_API_KEY`
from the environment):

```bash
export DEEPSEEK_API_KEY=sk-...
python3 api_balances.py
```

In the interactive TUI:
- `r` — refresh all values
- `q` — quit

Print the table once and exit (no curses, good for scripts/CI):

```bash
python3 api_balances.py --once
```

Use a custom config file:

```bash
python3 api_balances.py --config api_balances.example.json --once
```

## Configuration format

Config is a JSON file containing a list of API definitions:

```json
[
  {
    "name": "DeepSeek",
    "url": "https://api.deepseek.com/user/balance",
    "env_var": "DEEPSEEK_API_KEY",
    "auth": "bearer",
    "value_path": "balance_infos[0].total_balance"
  }
]
```

Fields:
- `name` (required): Display name for the NAME column.
- `url` (required): Full GET URL to call.
- `env_var` (optional): Environment variable holding a secret.
- `auth` (optional): Set to `"bearer"` to send
  `Authorization: Bearer <env_var value>`.
- `headers` (optional): Extra static request headers.
- `value_path` (required for meaningful output): Dot-path expression
  to extract a value from the parsed JSON response. Supports:
  - `a.b.c` — nested dict keys
  - `items[0].v` — explicit list index
  - `items[].v` — empty brackets mean "first element"

## Errors

- Missing config file, invalid JSON, or malformed entries produce a
  clear error message and non-zero exit before the TUI starts.
- Per-API errors (missing env var, HTTP failure, invalid JSON,
  bad `value_path`) are shown inline in the VALUE column as
  `ERROR: <message>` rather than crashing the app.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
