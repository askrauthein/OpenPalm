# OpenPalm

Python CLI for macOS that connects to WhatsApp (via `neonize`) and executes shell commands sent by you to your own chat when AI mode is enabled.

## Installation (macOS)

```bash
./scripts/install_macos.sh
```

This installer:

- installs `libmagic` via Homebrew (native dependency required by `neonize`)
- creates `.venv`
- installs the `openpalm` package and dependencies
- creates the `openpalm` launcher at `~/.local/bin/openpalm`

## Features

- QR code login (`neonize` adapter)
- Local session persistence
- Persistent `/ai enable` and `/ai disable` interpreter state
- Command execution with timeout, `stdout`/`stderr`, `exit code`, and output truncation
- Simple `message_id` deduplication
- Rotating local logs

## Run

```bash
python -m openpalm run
```

or

```bash
openpalm run
```

## CLI Commands

- `openpalm run`
- `openpalm login [--reset-session]`
- `openpalm status`
- `openpalm logout`

## Configuration

By default, the app uses:

- `~/.config/openpalm/config.toml`
- `~/.config/openpalm/state.json`
- `~/.config/openpalm/processed_messages.json`
- `~/.config/openpalm/app.log`

You can edit `config.toml` to adjust shell, timeout, working directory, and output limit.

## neonize note

The `channel_client.py` module contains a functional adapter for events and message sending. Integration details depend on the installed `neonize` API version.

## Project/Task Module

The listener now supports project, agent, task, and job orchestration commands via WhatsApp:

- `/project add-local <project_id> <path>`
- `/project add-github <project_id> <clone_url>`
- `/project list`
- `/project info <project_id>`
- `/project use <project_id>`
- `/project current`
- `/project remove <project_id>`
- `/project checkout <project_id> [branch=<name>|tag=<name>|commit=<sha>]`
- `/project update <project_id>`

- `/agent enable`
- `/agent disable`
- `/agent use codex|claude-code`
- `/agent current`

- `/task project=<project_id> agent=<agent> [ref=<ref>] <instruction>`
- `/task agent=<agent> <instruction>` (uses current project)

- `/job list`
- `/job status <job_id>`
- `/job result <job_id>`
- `/job logs <job_id>`
- `/job cancel <job_id>`

Persistence paths for this module:

- `~/.config/whats-agent/projects.toml`
- `~/.config/whats-agent/state.json`
- `~/.config/whats-agent/jobs.db`
- `~/.config/whats-agent/logs/`
- `~/.cache/whats-agent/repos/`
- `~/.cache/whats-agent/jobs/`
