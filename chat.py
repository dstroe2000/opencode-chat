#!/usr/bin/env python3
"""opencode-chat — A terminal chat client for OpenCode."""

import os
import sys
import signal
import subprocess
import time
import atexit
import json

from opencode_ai import Opencode, APIConnectionError, APIStatusError
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

# ---------------------------------------------------------------------------
# Section A: Globals
# ---------------------------------------------------------------------------

SERVE_PORT = 54321
DEFAULT_PROVIDER = "opencode"
DEFAULT_MODEL = "kimi-k2.5-free"
console = Console()
oc_process = None
client = None
session_id = None
provider_id = None
model_id = None


def find_opencode_port():
    """Try to find a running OpenCode server by checking common ports."""
    test_client = Opencode(base_url=os.environ.get("OPENCODE_BASE_URL"))
    try:
        test_client.session.list()
        return test_client
    except Exception:
        pass

    # Check if there's a server on a non-default port by scanning known ports
    for port in [SERVE_PORT, 4096, 3000, 8080]:
        try:
            test_client = Opencode(base_url=f"http://127.0.0.1:{port}")
            test_client.session.list()
            return test_client
        except Exception:
            pass

    return None

# ---------------------------------------------------------------------------
# Section B: OpenCode process management
# ---------------------------------------------------------------------------


def start_opencode():
    """Spawn 'opencode serve' and wait for it to become healthy."""
    global oc_process, client
    console.print("[dim]Starting OpenCode server...[/dim]")
    try:
        oc_process = subprocess.Popen(
            ["opencode", "serve", "--port", str(SERVE_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/] 'opencode' not found. "
            "Install it from https://github.com/sst/opencode"
        )
        sys.exit(1)

    atexit.register(cleanup_opencode)
    client = Opencode(base_url=f"http://127.0.0.1:{SERVE_PORT}")

    # Poll until healthy (up to 15s) using /session as health check
    for i in range(30):
        time.sleep(0.5)
        try:
            client.session.list()
            console.print("[dim]OpenCode server is ready.[/dim]")
            return
        except Exception:
            pass

    console.print("[bold red]Error:[/] OpenCode server failed to start within 15s.")
    cleanup_opencode()
    sys.exit(1)


def cleanup_opencode():
    """Terminate the OpenCode subprocess."""
    global oc_process
    if oc_process is None:
        return
    try:
        oc_process.terminate()
        oc_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        oc_process.kill()
        oc_process.wait()
    except Exception:
        pass
    oc_process = None


def ensure_opencode():
    """Make sure OpenCode is reachable; start it if not. Discover provider/model."""
    global client, provider_id, model_id

    # Try to find an already-running OpenCode server
    found = find_opencode_port()
    if found:
        client = found
        console.print("[dim]Connected to existing OpenCode server.[/dim]")
    else:
        start_opencode()

    # Use hardcoded default, validate it exists
    provider_id = DEFAULT_PROVIDER
    model_id = DEFAULT_MODEL
    try:
        providers_resp = client.app.providers()
        known = {p.id: p for p in providers_resp.providers}
        if provider_id in known and model_id in known[provider_id].models:
            console.print(f"[dim]Using {provider_id}/{model_id}[/dim]")
        else:
            console.print(
                f"[yellow]Warning:[/] {provider_id}/{model_id} not found on server, "
                f"using anyway. Run /models to see available options."
            )
    except Exception as e:
        console.print(f"[yellow]Could not verify model:[/] {e}")
        console.print(f"[dim]Using {provider_id}/{model_id}[/dim]")


# ---------------------------------------------------------------------------
# Section C: Display rendering
# ---------------------------------------------------------------------------


def display_response(sid):
    """Fetch messages for a session and render the last assistant response."""
    try:
        messages = client.session.messages(sid)
    except Exception as e:
        console.print(f"[bold red]Error fetching messages:[/] {e}")
        return

    # Find the last assistant message
    last_assistant = None
    for msg in reversed(messages):
        if msg.info.role == "assistant":
            last_assistant = msg
            break

    if last_assistant is None:
        console.print("[dim]No assistant response found.[/dim]")
        return

    # Render error if present
    if last_assistant.info.error is not None:
        render_error(last_assistant.info.error)

    # Dispatch each part
    for part in last_assistant.parts:
        ptype = part.type
        if ptype == "text":
            render_text(part)
        elif ptype == "tool":
            render_tool(part)
        elif ptype == "step-start":
            render_step_start(part)
        elif ptype == "step-finish":
            render_step_finish(part)
        elif ptype == "reasoning":
            render_reasoning(part)
        else:
            # file, snapshot, patch — show minimal info
            console.print(f"[dim]  [{ptype}][/dim]")


def render_text(part):
    """Render a text part as rich markdown."""
    if part.text:
        console.print()
        console.print(Markdown(part.text))
        console.print()


def render_tool(part):
    """Render a tool call as a rich panel."""
    state = part.state
    status = state.status

    # Status indicator
    if status == "completed":
        icon = "[green]✅ completed[/green]"
    elif status == "error":
        icon = "[red]❌ error[/red]"
    elif status == "running":
        icon = "[yellow]⏳ running[/yellow]"
    else:
        icon = "[dim]⏳ pending[/dim]"

    lines = [f"Status: {icon}"]

    # Title (from completed/running state)
    title_str = getattr(state, "title", None)
    if title_str:
        lines.insert(0, f"[bold]{title_str}[/bold]")

    # Input args
    input_data = getattr(state, "input", None)
    if input_data:
        try:
            if isinstance(input_data, dict):
                formatted = json.dumps(input_data, indent=2)
            else:
                formatted = str(input_data)
            if len(formatted) > 300:
                formatted = formatted[:300] + "..."
            lines.append(f"[dim]Input:[/dim] {formatted}")
        except Exception:
            pass

    # Output (completed only)
    output = getattr(state, "output", None)
    if output:
        truncated = output if len(output) <= 500 else output[:500] + "..."
        lines.append(f"[dim]Output:[/dim] {truncated}")

    # Error message (error state)
    error_msg = getattr(state, "error", None)
    if error_msg:
        lines.append(f"[red]Error: {error_msg}[/red]")

    content = "\n".join(lines)
    console.print(Panel(content, title=f"Tool: {part.tool}", border_style="cyan"))


def render_step_start(part):
    """Render a step-start marker."""
    console.print("[dim italic]  ── step started ──[/dim italic]")


def render_step_finish(part):
    """Render a step-finish marker with cost/token summary."""
    tokens = part.tokens
    cost = part.cost
    token_count = int(tokens.input + tokens.output)
    console.print(
        f"[dim italic]  ── step finished "
        f"({token_count} tokens, ${cost:.4f}) ──[/dim italic]"
    )


def render_reasoning(part):
    """Render a reasoning/thinking part."""
    text = getattr(part, "text", None)
    if text:
        truncated = text if len(text) <= 300 else text[:300] + "..."
        console.print(Panel(truncated, title="Thinking", border_style="dim"))


def render_error(error):
    """Render an assistant-level error."""
    name = getattr(error, "name", "Error")
    data = getattr(error, "data", None)

    if name == "MessageAbortedError":
        console.print(Panel("[yellow]Request was aborted.[/yellow]", border_style="yellow"))
    elif name == "ProviderAuthError":
        msg = data.message if hasattr(data, "message") else str(data)
        pid = data.provider_id if hasattr(data, "provider_id") else ""
        console.print(
            Panel(
                f"[red]Authentication error with provider '{pid}':\n{msg}[/red]",
                border_style="red",
            )
        )
    else:
        msg = data.message if hasattr(data, "message") else str(data)
        console.print(Panel(f"[red]{name}: {msg}[/red]", border_style="red"))


# ---------------------------------------------------------------------------
# Section D: REPL & commands
# ---------------------------------------------------------------------------


def send_message(text):
    """Send a message to the current session and display the response."""
    global session_id
    try:
        console.print("[dim]Thinking...[/dim]")
        client.session.chat(
            session_id,
            model_id=model_id,
            provider_id=provider_id,
            parts=[{"type": "text", "text": text}],
            timeout=300,
        )
        display_response(session_id)

    except KeyboardInterrupt:
        console.print("\n[yellow]Aborting...[/yellow]")
        try:
            client.session.abort(session_id)
        except Exception:
            pass
        # Show whatever partial response exists
        display_response(session_id)

    except APIConnectionError:
        console.print("[bold red]Lost connection to OpenCode server.[/bold red]")

    except APIStatusError as e:
        console.print(f"[bold red]API error ({e.status_code}):[/] {e.message}")

    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")


def create_session():
    """Create a new chat session."""
    global session_id
    try:
        session = client.session.create(extra_body={})
        session_id = session.id
        console.print(f"[dim]Session: {session_id[:8]}...[/dim]")
    except Exception as e:
        console.print(f"[bold red]Error creating session:[/] {e}")
        sys.exit(1)


def handle_command(cmd):
    """Handle a slash command."""
    raw = cmd.strip()
    cmd = raw.lower()

    if cmd in ("/quit", "/exit"):
        console.print("Goodbye!")
        cleanup_opencode()
        sys.exit(0)

    elif cmd == "/new":
        create_session()
        console.print("[green]New session created.[/green]")

    elif cmd == "/history":
        show_history()

    elif cmd == "/sessions":
        list_sessions()

    elif cmd == "/models":
        show_models()

    elif cmd.startswith("/model "):
        switch_model(raw[7:].strip())

    elif cmd == "/model":
        console.print(f"[bold]Current:[/] {provider_id}/{model_id}")
        console.print("[dim]Usage: /model <provider>/<model_id>[/dim]")

    elif cmd == "/abort":
        try:
            client.session.abort(session_id)
            console.print("[yellow]Aborted.[/yellow]")
        except Exception as e:
            console.print(f"[red]Abort failed:[/] {e}")

    elif cmd == "/help":
        show_help()

    else:
        console.print(f"[red]Unknown command:[/] {cmd}. Type /help for commands.")


def show_history():
    """Display all messages in the current session."""
    try:
        messages = client.session.messages(session_id)
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        return

    if not messages:
        console.print("[dim]No messages yet.[/dim]")
        return

    for msg in messages:
        role = msg.info.role
        if role == "user":
            # Show user message text parts
            for part in msg.parts:
                if part.type == "text":
                    console.print(f"[bold green]You>[/] {part.text}")
        else:
            # Show assistant text parts (abbreviated)
            for part in msg.parts:
                if part.type == "text" and part.text:
                    text = part.text
                    if len(text) > 200:
                        text = text[:200] + "..."
                    console.print(f"[bold blue]Assistant>[/] {text}")
                elif part.type == "tool":
                    status = part.state.status
                    console.print(f"  [cyan]Tool: {part.tool} ({status})[/cyan]")
        console.print()


def list_sessions():
    """List all available sessions."""
    try:
        sessions = client.session.list()
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        return

    if not sessions:
        console.print("[dim]No sessions.[/dim]")
        return

    table = Table(title="Sessions")
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("Title", style="white")
    table.add_column("Active", style="green")

    for s in sessions:
        sid = s.id[:8] + "..."
        title = s.title or "(untitled)"
        active = "→" if s.id == session_id else ""
        table.add_row(sid, title, active)

    console.print(table)


def show_models():
    """List all available providers and models."""
    try:
        providers_resp = client.app.providers()
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        return

    defaults = providers_resp.default or {}

    for p in providers_resp.providers:
        is_active_provider = p.id == provider_id
        header = f"[bold]{p.name}[/bold] [dim]({p.id})[/dim]"
        if defaults.get(p.id):
            header += f"  [dim]default: {defaults[p.id]}[/dim]"
        console.print(header)

        if not p.models:
            console.print("  [dim](no models)[/dim]")
            continue

        for mid, m in p.models.items():
            active = ""
            if is_active_provider and mid == model_id:
                active = " [green]← active[/green]"
            cost_str = ""
            if hasattr(m, "cost") and m.cost:
                cost_str = f"[dim] (${m.cost.input}/M in, ${m.cost.output}/M out)[/dim]"
            console.print(f"  {p.id}/{mid}{cost_str}{active}")

        console.print()


def switch_model(spec):
    """Switch the active provider/model. Accepts 'provider/model' or just 'model'."""
    global provider_id, model_id

    try:
        providers_resp = client.app.providers()
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        return

    if "/" in spec:
        new_provider, new_model = spec.split("/", 1)
    else:
        # Search all providers for a matching model ID
        new_provider = None
        new_model = spec
        for p in providers_resp.providers:
            if spec in p.models:
                new_provider = p.id
                break
        if not new_provider:
            console.print(f"[red]Model '{spec}' not found in any provider.[/red]")
            console.print("[dim]Use /models to see available options.[/dim]")
            return

    # Validate provider exists
    known = {p.id: p for p in providers_resp.providers}
    if new_provider not in known:
        console.print(f"[red]Provider '{new_provider}' not found.[/red]")
        console.print(f"[dim]Available: {', '.join(known.keys())}[/dim]")
        return

    # Validate model exists in that provider
    if new_model not in known[new_provider].models:
        available = list(known[new_provider].models.keys())
        console.print(f"[red]Model '{new_model}' not found in {new_provider}.[/red]")
        console.print(f"[dim]Available: {', '.join(available[:10])}[/dim]")
        return

    provider_id = new_provider
    model_id = new_model
    console.print(f"[green]Switched to {provider_id}/{model_id}[/green]")


def show_help():
    """Display available commands."""
    table = Table(title="Commands")
    table.add_column("Command", style="cyan")
    table.add_column("Description")
    table.add_row("/help", "Show this help message")
    table.add_row("/new", "Start a new chat session")
    table.add_row("/history", "Show messages in the current session")
    table.add_row("/sessions", "List all sessions")
    table.add_row("/models", "List all available providers and models")
    table.add_row("/model", "Show current model")
    table.add_row("/model <provider>/<id>", "Switch model (e.g. /model anthropic/claude-3-5-haiku-latest)")
    table.add_row("/abort", "Abort the current request")
    table.add_row("/quit", "Clean up and exit (also /exit)")
    console.print(table)


def repl():
    """Main input loop."""
    while True:
        try:
            text = console.input("[bold green]You>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break

        if not text:
            continue

        if text.startswith("/"):
            handle_command(text)
        else:
            send_message(text)


def main():
    """Entry point."""
    console.print(
        Panel(
            "[bold]opencode-chat[/bold]\n"
            "Terminal chat client for OpenCode\n"
            "Type [cyan]/help[/cyan] for commands, [cyan]/quit[/cyan] to exit",
            border_style="green",
        )
    )

    ensure_opencode()
    create_session()
    repl()
    cleanup_opencode()


if __name__ == "__main__":
    main()
