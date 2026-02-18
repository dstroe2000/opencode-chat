# Architecture

## Overview

opencode-chat is a single-file Python CLI app (~210 lines) that uses the `opencode-ai` SDK to communicate with OpenCode's REST API and `rich` for terminal rendering.

## Decision Log

| # | Decision | Chosen | Alternatives Considered | Rationale |
|---|----------|--------|------------------------|-----------|
| 1 | SDK | `opencode-ai` (anomalyco, v0.1.0a36) | `ai4pa-opencode-sdk` (v0.11.0) | Better documented, actively maintained |
| 2 | App type | Chat CLI tool | Code review helper; Session dashboard | Most direct use of the SDK's capabilities |
| 3 | Interaction | Interactive REPL | One-shot command; Both modes | Natural for chat; one-shot can be added later |
| 4 | Tool display | Show everything (calls, args, states, results) | Minimal indicators; Final response only | Full visibility into agent behavior is the key feature |
| 5 | Terminal UI | `rich` library | Plain text; Textual TUI | Good balance of visual quality and simplicity |
| 6 | OpenCode mgmt | Auto-start if not running | Error if not running | Better UX — just works out of the box |
| 7 | Architecture | Single file, two dependencies | Multi-module package | Simple enough to not need structure overhead |
| 8 | Response retrieval | Polling (`session.messages()` after chat) | SSE streaming (real-time) | Simpler; streaming needs threading/asyncio |

## System Architecture

```
┌──────────┐     ┌──────────────┐     ┌───────────────────┐     ┌──────────────┐
│  User    │────▶│  REPL Loop   │────▶│  opencode-ai SDK  │────▶│  OpenCode    │
│ (stdin)  │     │  (chat.py)   │     │  (HTTP client)    │     │  REST API    │
│          │◀────│              │◀────│                   │◀────│  :54321      │
└──────────┘     └──────────────┘     └───────────────────┘     └──────┬───────┘
                        │                                              │
                        │ rich panels                                  │
                        ▼                                              ▼
                 ┌──────────────┐                              ┌──────────────┐
                 │  Terminal    │                              │  LLM Provider│
                 │  (stdout)   │                              │  (Anthropic, │
                 └──────────────┘                              │   OpenAI..)  │
                                                              └──────────────┘
```

## Data Flow

1. User types a message at the `You>` prompt
2. REPL dispatches to `send_message()` (or `handle_command()` for `/` prefixed input)
3. `send_message()` calls `client.session.chat(session_id, model_id=..., provider_id=..., parts=[{"type":"text","text":"..."}])` with a 5-minute timeout
4. The SDK makes a POST to OpenCode's REST API, which forwards to the configured LLM provider
5. OpenCode orchestrates tool calls (file reads, searches, edits) and returns the final response
6. `session.chat()` returns an `AssistantMessage` (metadata only — cost, tokens, error)
7. `display_response()` calls `client.session.messages(session_id)` to fetch all messages
8. It finds the last assistant message and iterates over its parts, dispatching each to a renderer:
   - `text` → `render_text()` → Rich Markdown
   - `tool` → `render_tool()` → Rich Panel with name, args, status, output
   - `step-start` / `step-finish` → `render_step()` → dim italic status line
9. Errors are caught and rendered via `render_error()`

## SDK Constraints

1. **`session.chat()` signature**: Requires `model_id`, `provider_id`, and `parts` (not a simple string). Parts must be `[{"type": "text", "text": "..."}]`
2. **`AssistantMessage` has no parts**: Only metadata (cost, tokens, error). Actual response parts come from `session.messages(session_id)` after the chat call completes
3. **Default port**: SDK hardcodes `http://localhost:54321` as base URL
4. **Provider discovery**: `client.app.providers()` returns default provider/model mapping needed for chat calls

## Component Breakdown

| Section | Responsibility | Key Functions |
|---------|---------------|---------------|
| A: Imports & Globals | Dependencies, module state | — |
| B: Process Management | Start/stop OpenCode subprocess, health check | `start_opencode()`, `cleanup_opencode()`, `ensure_opencode()` |
| C: Display Rendering | Convert response parts to rich terminal output | `display_response()`, `render_text()`, `render_tool()`, `render_step()`, `render_error()` |
| D: REPL & Commands | User interaction loop, command dispatch, message sending | `send_message()`, `handle_command()`, `create_session()`, `repl()`, `main()` |

## Future Considerations

- **SSE streaming**: Real-time tool call updates as they happen (requires threading or asyncio)
- **Async client**: The SDK supports async — could improve responsiveness
- **Multi-session tabs**: Switch between sessions without creating new ones
- **Configuration file**: Persist preferences (model, provider, display settings)
