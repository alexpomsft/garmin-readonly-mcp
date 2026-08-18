# Security Policy

## Sensitive material

Never submit Garmin passwords, MFA codes, cookies, OAuth/session tokens, raw Garmin
responses, profile information, GPS tracks, or populated SQLite caches in issues,
pull requests, logs, tests, or chat.

Authentication must happen interactively in a private local terminal. The project does
not accept credentials through CLI arguments, environment variables, MCP tool arguments,
or source-controlled configuration.

The default private state is outside the repository at
`~/.local/share/garmin-readonly-mcp`. Token files and the normalized cache are ignored by
Git and restricted to the current user.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's security-advisory interface for this
repository. Include reproduction steps using synthetic data only. Do not open a public
issue containing credentials, tokens, personal health information, account identifiers,
or Garmin response payloads.

## Supported version

Until tagged releases exist, only the latest commit on `main` is supported.

## Threat model and non-goals

The project minimizes exposure by separating the networked synchronization worker from
the cache-only MCP server. It does not attempt to defend against a compromised operating
system account, a malicious Python dependency, or an attacker with access to the user's
unlocked local session.

Garmin Connect access is based on undocumented community endpoints. This carries
availability, terms-of-use, rate-limit, challenge, and account-lockout risk. Use the
official Garmin Connect Developer Program when eligible.
