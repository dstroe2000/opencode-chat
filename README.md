# opencode-chat

A terminal chat client for [OpenCode](https://github.com/sst/opencode), the open-source AI coding agent.

Interactive REPL that connects to OpenCode via the `opencode-ai` Python SDK, sends messages, and displays responses with full tool call visibility — file reads, searches, and code edits are shown as rich terminal panels.

## Prerequisites

- Python 3.8+
- OpenCode installed ([installation guide](https://github.com/sst/opencode#installation))

## Installation

```bash
cd opencode-chat
pip install -r requirements.txt
```

## Usage

```bash
python chat.py
```

The app will auto-start OpenCode's API server if it's not already running, then open an interactive chat session.

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/new` | Start a new chat session |
| `/history` | Show messages in the current session |
| `/sessions` | List all sessions |
| `/models` | List all providers and models with pricing |
| `/model` | Show the currently active model |
| `/model <provider>/<id>` | Switch model (e.g. `/model anthropic/claude-3-5-haiku-latest`) |
| `/abort` | Abort the current request |
| `/quit` | Clean up and exit (also `/exit`) |

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `OPENCODE_BASE_URL` | `http://localhost:54321` | Override the OpenCode API base URL |

## Example Session

```
╭─ opencode-chat ──────────────────────────╮
│ Terminal chat client for OpenCode         │
│ Type /help for commands, /quit to exit    │
╰──────────────────────────────────────────╯

You> Find all Python files that import requests

╭─ Tool: glob ─────────────────────────────╮
│ Pattern: **/*.py                          │
│ Status: ✅ completed (12 files found)     │
╰──────────────────────────────────────────╯
╭─ Tool: grep ─────────────────────────────╮
│ Pattern: import requests                  │
│ Status: ✅ completed (3 matches)          │
╰──────────────────────────────────────────╯

I found 3 Python files that import requests:
- src/api/client.py
- scripts/download.py
- tests/test_api.py

You> /quit
Goodbye!
```
