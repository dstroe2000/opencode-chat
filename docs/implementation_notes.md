# Implementation Notes

Gotchas discovered during integration testing of `opencode-ai` SDK (v0.1.0a36) against OpenCode server (v1.2.6). These are undocumented behaviors that differ from what the SDK's type signatures suggest.

## 1. The `/app` endpoint doesn't exist on the server

The SDK provides `client.app.get()` which hits `GET /app`. The server has no such route — it falls through to the SPA (web UI) fallback and returns HTML. The SDK doesn't raise an error; it silently returns the HTML string.

**Impact**: Cannot use `app.get()` as a health check.
**Workaround**: Use `client.session.list()` (`GET /session`) instead — it always returns JSON.

## 2. `session.create()` requires a JSON body

The SDK's `session.create()` sends a `POST /session` with no request body. The server rejects this with `400 Malformed JSON in request body`.

**Workaround**: Pass `extra_body={}` to force an empty JSON body:
```python
session = client.session.create(extra_body={})
```

## 3. `session.chat()` response doesn't match `AssistantMessage`

The SDK declares that `session.chat()` returns an `AssistantMessage`, but the server actually returns a `SessionMessagesResponseItem` structure:

```json
{
  "info": { "role": "assistant", "cost": 0, "tokens": {...}, ... },
  "parts": [ { "type": "text", "text": "..." }, ... ]
}
```

The SDK tries to parse this as `AssistantMessage` (which expects `role`, `cost`, `tokens` at the top level, not nested under `info`), so all fields come back as `None`.

**Impact**: Cannot use the return value of `session.chat()` for cost/token/error data.
**Workaround**: Ignore the return value. Call `client.session.messages(session_id)` afterward to get properly parsed messages and parts.

## 4. Server may override your model/provider selection

Even when you explicitly pass `model_id` and `provider_id` to `session.chat()`, the server may use a different model. In testing, requests for `anthropic/claude-sonnet-4-6` were served by `opencode/kimi-k2.5-free`.

This may be related to:
- The OpenCode Zen free tier routing
- Mode-based model selection (`"mode": "build"` in the response)
- The requested model ID not being in the provider's model list (the `default` dict may reference model aliases that don't appear in `provider.models`)

**Impact**: You can't guarantee which model handles your request.
**Workaround**: None found. The model selection appears to be server-side. Check `response.info.modelID` in the messages response to see what was actually used.

## 5. The `default` dict maps provider IDs to model IDs

`client.app.providers().default` is `Dict[str, str]` with format `{"provider_id": "model_id"}`:

```python
{
    "opencode": "gemini-3-pro",
    "anthropic": "claude-sonnet-4-6",
    "ollama_R": "big256k-nemotron-3-nano:latest",
    ...
}
```

Note: the model IDs in `default` may not exist in the corresponding provider's `models` dict. For example, `claude-sonnet-4-6` appears in `default` but the anthropic provider's model list has `claude-opus-4-5-20251101`, `claude-3-5-haiku-latest`, etc. These may be server-side aliases.

## 6. Server uses a random port by default

`opencode serve` defaults to `--port 0` (random port), not port 54321. The SDK defaults to `http://localhost:54321`. If you start the server without `--port 54321`, the SDK can't find it.

**Workaround**: Always pass `--port 54321` when starting the server, or scan for running instances. The app scans ports 54321, 4096, 3000, and 8080. The `opencode web` command also starts a server (commonly on port 4096).

## 7. The `reasoning` part type exists but isn't in the SDK types

The server returns `"type": "reasoning"` parts containing the model's chain-of-thought. The SDK's `Part` union type doesn't include a `ReasoningPart`, but the SDK still parses it as a generic object with `.type` and `.text` attributes.

```json
{
    "type": "reasoning",
    "text": "The user wants me to...",
    "time": { "start": ..., "end": ... }
}
```

**Impact**: No type-safe access, but `part.type == "reasoning"` and `part.text` work fine.

## 8. Several SDK endpoints return HTML (no server route)

These SDK methods hit paths that fall through to the SPA:
- `client.app.get()` → `GET /app` → HTML
- `client.app.modes()` → `GET /mode` → HTML

The server's actual routes don't match the SDK paths for these endpoints. Only these are confirmed working:
- `GET /session` — list sessions
- `POST /session` — create session (with JSON body)
- `GET /session/{id}/message` — get messages
- `POST /session/{id}/message` — send chat
- `POST /session/{id}/abort` — abort
- `GET /config/providers` — list providers
- `GET /config` — get config
