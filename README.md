# Garmin Read-Only MCP

A deliberately narrow Garmin Connect integration for local use with Hermes Agent.
It synchronizes selected Garmin summaries into an owner-only SQLite cache, then serves
only that normalized cache through three read-only MCP tools.

> This project uses the community-maintained `python-garminconnect` client and
> undocumented Garmin Connect endpoints. It is not affiliated with or supported by
> Garmin. Endpoints may change, and automated access may carry account or terms-of-use
> risk. The official Garmin Connect Developer Program remains the preferred route for
> approved business integrations.

## Security model

The design separates network access from the MCP process:

1. `garmin-readonly-auth` performs a one-time interactive login in a local terminal.
   Password and MFA input are hidden and never accepted as command arguments.
2. `garmin-readonly-sync` loads reusable local session material, fetches a bounded date
   window, strips upstream fields, and writes normalized summaries to SQLite.
3. `garmin-readonly-mcp` imports neither the Garmin client nor session material. It reads
   only the normalized SQLite cache and refuses caches that are symlinks, non-regular,
   not owned by the current user, or accessible by group/other users.

The default state directory is:

```text
~/.local/share/garmin-readonly-mcp/
├── tokens/          # Garmin session material, mode 0700/0600
└── cache.sqlite3    # normalized cache, mode 0600
```

Set the non-secret `GARMIN_READONLY_HOME` environment variable to use another root.
Never place the state directory inside the repository.

## Data scope

The cache and MCP expose only:

- Daily total, active, and BMR/resting calories
- Steps and resting heart rate when available
- Activity type, start time, duration, distance, and calories
- Sleep duration/score, Body Battery, nightly HRV/status, and training readiness when
  available

They deliberately exclude:

- Garmin profile and social data
- Account identifiers and activity IDs
- Device details
- GPS coordinates, routes, and FIT/GPX/TCX files
- Weight and body composition
- Raw Garmin responses
- Upload, update, schedule, or deletion operations
- Generic or arbitrary Garmin API access

Garmin calorie values are activity context, not a command to increase food intake.

## Requirements

- Linux or another Unix-like environment with private file permissions
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- A Garmin Connect account

## Install

```bash
git clone https://github.com/alexpomsft/garmin-readonly-mcp.git
cd garmin-readonly-mcp
uv sync --frozen
```

## Authenticate locally

Run this in a private local terminal—not Telegram, chat, shell history, or a shared
screen:

```bash
uv run garmin-readonly-auth
```

The command asks locally for email, hidden password, and hidden MFA if Garmin requires
it. It stores reusable session material but not the password.

## Synchronize

The default synchronizes today and yesterday:

```bash
uv run garmin-readonly-sync
```

A bounded historical window can be requested:

```bash
uv run garmin-readonly-sync --end-date 2026-08-18 --days 14
```

`--days` must be between 1 and 31. Provider errors are replaced with a fixed public
message so raw Garmin responses and authentication details are not echoed.

## Run the MCP server

After at least one successful synchronization:

```bash
uv run garmin-readonly-mcp
```

The stdio server exposes exactly:

- `get_daily_activity(date: YYYY-MM-DD)`
- `get_recent_activities(days: 1..31 = 7)`
- `get_recovery_summary(date: YYYY-MM-DD)`

Tool schemas reject undeclared arguments.

## Connect to Hermes Agent

Use Hermes' MCP command rather than editing `config.yaml` manually:

```bash
hermes mcp add garmin-readonly \
  --command /absolute/path/to/garmin-readonly-mcp/.venv/bin/garmin-readonly-mcp
hermes mcp test garmin-readonly
```

Restart Hermes after adding the server so its tools are discovered. No credentials or
session-token paths are passed to the MCP configuration; it uses the private default
state root. If `GARMIN_READONLY_HOME` is customized, pass only that non-secret setting
with `hermes mcp add ... --env GARMIN_READONLY_HOME=/private/path`.

## Development and verification

```bash
uv sync --frozen
uv run pytest --cov=garmin_readonly_mcp --cov-report=term-missing
uv run ruff check .
uv run mypy src tests
uv run pip-audit
```

The implementation was developed with failing tests first. CI runs the same test,
lint, type-check, and dependency-audit gates.

## Limitations

- Garmin Connect endpoints are reverse-engineered and can break without notice.
- Garmin may rate-limit, challenge, or lock automated clients.
- Some recovery fields are unavailable on some devices or dates and return `null`.
- The local cache is a snapshot; schedule `garmin-readonly-sync` separately if fresher
  data is needed.
- This project does not automatically modify calorie targets or provide medical advice.

See [SECURITY.md](SECURITY.md) for credential handling and vulnerability reporting.
