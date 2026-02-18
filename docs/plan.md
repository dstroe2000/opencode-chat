# Implementation Plan

## Build Order

### Step 1: Project Setup
- Create project directory and `requirements.txt`
- Install dependencies: `pip install --pre opencode-ai rich`

### Step 2: Section A — Imports & Globals (~20 lines)
- Import stdlib: `os`, `sys`, `signal`, `subprocess`, `time`, `atexit`, `json`
- Import SDK: `Opencode`, `APIConnectionError` from `opencode_ai`
- Import SDK types: `TextPart`, `ToolPart`, `StepStartPart`, `StepFinishPart`
- Import rich: `Console`, `Markdown`, `Panel`
- Initialize module state: `console`, `oc_process`, `client`, `session_id`, `provider_id`, `model_id`

**Checkpoint**: File runs without import errors

### Step 3: Section B — Process Management (~50 lines)

**`start_opencode()`**
- Spawn `opencode serve --port 54321` via `subprocess.Popen`
- Register `cleanup_opencode()` with `atexit`
- Poll health check (`client.app.get()`) for up to 10 seconds

**`cleanup_opencode()`**
- `process.terminate()` → `process.wait(timeout=5)` → `process.kill()` on timeout

**`ensure_opencode()`**
- Try `client.app.get()` as health check
- On `APIConnectionError`: call `start_opencode()`
- Discover default provider/model via `client.app.providers()`

**Checkpoint**: `python -c "from chat import ensure_opencode; ensure_opencode()"` starts OpenCode

### Step 4: Section C — Display Rendering (~65 lines)

**`display_response(session_id)`**
- Call `client.session.messages(session_id)`
- Find last assistant message (iterate from end)
- Dispatch each part by `part.type`

**`render_text(part)`**
- Extract `part.text`, render as `rich.markdown.Markdown`

**`render_tool(part)`**
- Panel with title = tool name
- Show input args (JSON formatted, truncated at 200 chars)
- Status icon: ✅ completed, ❌ error, ⏳ running
- Output preview (truncated at 300 chars)

**`render_step(part)`**
- Dim italic line: "Step started: {name}" or "Step finished: {name} ({tokens} tokens, ${cost})"

**`render_error(error)`**
- Red panel for errors, yellow for aborted

**Checkpoint**: Mock a response and verify rendering

### Step 5: Section D — REPL & Commands (~75 lines)

**`send_message(text)`**
```python
def send_message(text):
    response = client.session.chat(
        session_id,
        model_id=model_id,
        provider_id=provider_id,
        parts=[{"type": "text", "text": text}],
        timeout=300
    )
    display_response(session_id)
```
- Wrap in try/except for KeyboardInterrupt → `session.abort(session_id)`
- Handle API errors gracefully

**`handle_command(cmd)`**
- `/quit`, `/exit` → cleanup and `sys.exit(0)`
- `/new` → `create_session()`
- `/history` → fetch and display all messages in session
- `/sessions` → list all sessions with IDs and dates
- `/abort` → `client.session.abort(session_id)`
- `/help` → print command table

**`create_session()`**
- `client.session.create()` → store `session_id`

**`repl()`**
- Loop: `console.input("[bold green]You>[/] ")`
- Route to `handle_command()` or `send_message()`
- Handle `EOFError` (Ctrl+D) → exit
- Handle `KeyboardInterrupt` (Ctrl+C at prompt) → exit

**`main()`**
- Print banner panel
- Call `ensure_opencode()`
- Call `create_session()`
- Call `repl()`
- Cleanup on exit

**Checkpoint**: Full interactive session works

### Step 6: Documentation
- Write README.md
- Write architecture.md

### Step 7: End-to-End Testing
1. `python chat.py` — auto-starts OpenCode, shows banner
2. Send a message — see tool panels and response
3. `/sessions` — lists current session
4. `/new` — creates new session
5. `/history` — shows message history
6. Ctrl+C during response — aborts gracefully
7. `/quit` — cleans up and exits

## Known Blockers

- **SDK is alpha** (v0.1.0a36): May have breaking changes or undocumented behavior
- **Provider discovery format**: `providers_resp.default` structure not well-documented — may need runtime debugging
- **`opencode serve` syntax**: May vary between OpenCode versions
