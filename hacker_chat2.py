import sys
for _s in (sys.stdout, sys.stderr, sys.stdin):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

try:
    from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except ImportError:
    sys.exit("missing deps:  pip install openai rich")

try:
    import termios
    import tty
    HAS_TTY = True
except ImportError:
    HAS_TTY = False

BASE_URL = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")
MODELS = ["glm-4.7-flash", "glm-4.5-flash"]
STORE = Path.home() / ".glmc" / "sessions"
SYSTEM = (
    "You are GLM running inside glmc, a terminal agent on the user's machine. "
    "Answer in tight markdown. Prefer doing over explaining: when a question touches "
    "the filesystem, use read_file or list_dir instead of guessing. "
    "Use run_command only for read-only things unless the user asked for changes. "
    "Never repeat tool output verbatim; summarise."
)
TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file from the user's machine.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List a directory on the user's machine.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Run a shell command on the user's machine. The user must approve it.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
]

console = Console()
G = "bright_green"


def user_name():
    try:
        import getpass
        return getpass.getuser()
    except Exception:
        return "user"


def keypress():
    if not HAS_TTY or not sys.stdin.isatty():
        return console.input("[bold]?[/bold] ").strip().lower()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch.lower()


def ask(kind, detail):
    console.print(f"  [bold red]?[/bold red] [bold]{kind}[/bold] [dim]{detail}[/dim] "
                  f"[bold bright_green](y)[/bold bright_green]/[bold](n)[/bold] ", end="")
    a = keypress()
    console.print("[bright_green]yes[/bright_green]" if a == "y" else "[red]no[/red]")
    return a == "y"


def short(s, n):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def read_file(path):
    p = Path(path).expanduser()
    return p.read_bytes()[:40_000].decode("utf-8", errors="replace")


def list_dir(path):
    p = Path(path).expanduser()
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))[:300]
    return "\n".join(f"{'d' if i.is_dir() else '-'} {i.name}" for i in items)


def run_command(command):
    r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    out = (r.stdout + r.stderr).strip() or "(no output)"
    return f"exit={r.returncode}\n{out[:10_000]}"


TOOL_IMPL = {"read_file": read_file, "list_dir": list_dir, "run_command": run_command}


def do_tool(name, args):
    if name == "run_command" and not ask("run command", short(args.get("command", ""), 80)):
        return "denied by user"
    try:
        return TOOL_IMPL[name](**args)
    except Exception as e:
        return f"error: {e}"


def retryable(e):
    if isinstance(e, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(e, APIStatusError):
        return e.status_code in (429, 500, 502, 503, 504)
    text = str(e).lower()
    return "overloaded" in text or "rate" in text or "too many" in text


def stream_once(client, model, messages):
    text = []
    calls = {}
    with console.status(f"[{G}]thinking…[/{G}]", spinner="dots"):
        stream = client.chat.completions.create(
            model=model, messages=messages, tools=TOOLS, stream=True, timeout=120)
        for chunk in stream:
            if not chunk.choices:
                continue
            d = chunk.choices[0].delta
            if d.content:
                text.append(d.content)
                console.print(d.content, style=G, end="")
            for tc in d.tool_calls or []:
                slot = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["args"] += tc.function.arguments
    console.print()
    msg = {"role": "assistant", "content": "".join(text) or None}
    if calls:
        msg["tool_calls"] = [
            {"id": s["id"] or f"call_{i}", "type": "function",
             "function": {"name": s["name"], "arguments": s["args"] or "{}"}}
            for i, s in sorted(calls.items())]
    return msg


def respond(client, messages):
    chain = MODELS[:]
    attempt = 0
    while chain:
        model = chain[0]
        try:
            return stream_once(client, model, messages), model
        except Exception as e:
            if not retryable(e):
                console.print(f"\n[bold red]error[/bold red] {short(str(e), 200)}")
                return None, model
            attempt += 1
            wait = min(2 ** attempt, 12)
            if attempt >= 3 and len(chain) > 1:
                chain.pop(0)
                console.print(f"\n[dim]switching to {chain[0]}…[/dim]")
            else:
                console.print(f"\n[dim]busy · retry in {wait}s[/dim]")
            time.sleep(wait)
    console.print("\n[bold red]all models busy, try again soon[/bold red]")
    return None, MODELS[0]


def banner(model):
    t = Text()
    t.append("▐▛◤▙  glmc\n", style=f"bold {G}")
    t.append(f"   {model} · free tier · {user_name()}@local", style="dim")
    console.print(Panel(t, border_style=G, padding=(0, 2)))
    console.print(f"[dim] -c continue · -r resume · /help inside · /exit out[/dim]")
    console.print(Rule(style="dim green"))


def prompt():
    return console.input(f"\n[bold {G}]{user_name()}@local ❯[/bold {G}] ")


def save(messages, model, path=None):
    STORE.mkdir(parents=True, exist_ok=True)
    if path is None:
        first = next((m["content"] for m in messages if m["role"] == "user" and m["content"]), "chat")
        path = STORE / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps({
        "title": short(first, 60), "model": model,
        "saved": datetime.now().isoformat(timespec="seconds"),
        "messages": messages}, ensure_ascii=False, indent=1))
    return path


def sessions():
    if not STORE.exists():
        return []
    return sorted(STORE.glob("*.json"), reverse=True)


def pick_session():
    files = sessions()
    if not files:
        console.print("[dim]no saved sessions yet[/dim]")
        return None
    table = Table(box=None, pad_edge=False, show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("title", style=G)
    table.add_column("when", style="dim")
    for i, f in enumerate(files[:12], 1):
        d = json.loads(f.read_text())
        table.add_row(str(i), short(d.get("title", "?"), 48), d.get("saved", "?")[:16])
    console.print(table)
    n = console.input("[bold]resume #[/bold] ").strip()
    if n.isdigit() and 1 <= int(n) <= min(len(files), 12):
        return files[int(n) - 1]
    return None


def show_help():
    console.print(Panel(
        "[green]/file <path>  attach a file\n"
        "/tree [dir]   list a directory\n"
        "/model <id>   switch model\n"
        "/resume       load an older session\n"
        "/clear        fresh memory\n"
        "/log          memory size\n"
        "/exit         save and quit[/green]", title="help", border_style="dim green"))


def loop(client, messages, model):
    path = save(messages, model)
    while True:
        try:
            user = prompt().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]saved · bye[/dim]")
            break
        if not user:
            continue
        if user.startswith("/"):
            cmd, _, arg = user.partition(" ")
            if cmd == "/exit":
                console.print("[dim]saved · bye[/dim]")
                break
            if cmd == "/help":
                show_help()
            elif cmd == "/clear":
                messages = [{"role": "system", "content": SYSTEM}]
                console.print("[dim]memory cleared[/dim]")
            elif cmd == "/log":
                console.print(f"[dim]{len(messages)} messages in memory[/dim]")
            elif cmd == "/model":
                if arg:
                    MODELS.insert(0, arg.strip())
                    model = arg.strip()
                    console.print(f"[dim]model → {model}[/dim]")
                else:
                    console.print(f"[dim]model → {model}[/dim]")
            elif cmd == "/file":
                if not arg:
                    console.print("[red]/file needs a path[/red]")
                    continue
                try:
                    body = read_file(arg)
                    messages.append({"role": "user",
                                     "content": f"[file: {arg}]\n{body}"})
                    console.print(f"[dim]attached {arg} · {len(body)} chars[/dim]")
                except Exception as e:
                    console.print(f"[red]{e}[/red]")
            elif cmd == "/tree":
                console.print(Panel(list_dir(arg or "."), title=arg or ".",
                                    border_style="dim green"))
            elif cmd == "/resume":
                f = pick_session()
                if f:
                    d = json.loads(f.read_text())
                    messages = d["messages"]
                    model = d.get("model", model)
                    console.print(f"[dim]resumed · {d.get('title', '')}[/dim]")
            else:
                console.print("[red]unknown · /help[/red]")
            continue

        messages.append({"role": "user", "content": user})
        reply, used = respond(client, messages)
        if reply is None:
            messages.pop()
            continue
        messages.append(reply)
        for _ in range(12):
            if not reply.get("tool_calls"):
                break
            for tc in reply["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                console.print(f"  [dim]⏺ {tc['function']['name']} "
                              f"{short(json.dumps(args, ensure_ascii=False), 70)}[/dim]")
                out = do_tool(tc["function"]["name"], args)
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": out[:12_000]})
            reply, used = respond(client, messages)
            if reply is None:
                break
            messages.append(reply)
        save(messages, used, path)


def main():
    ap = argparse.ArgumentParser(prog="glmc")
    ap.add_argument("-c", "--continue", dest="cont", action="store_true")
    ap.add_argument("-r", "--resume", action="store_true")
    ap.add_argument("-m", "--model", default=os.environ.get("ZAI_MODEL", MODELS[0]))
    args = ap.parse_args()

    key = os.environ.get("ZAI_API_KEY")
    if not key:
        sys.exit("no key ·  export ZAI_API_KEY='youkey'")
    if args.model in MODELS:
        MODELS.remove(args.model)
    MODELS.insert(0, args.model)

    messages = [{"role": "system", "content": SYSTEM}]
    if args.cont and sessions():
        messages = json.loads(sessions()[0].read_text())["messages"]
    elif args.resume:
        f = pick_session()
        if f:
            messages = json.loads(f.read_text())["messages"]

    client = OpenAI(api_key=key, base_url=BASE_URL)
    banner(args.model)
    loop(client, messages, args.model)


if __name__ == "__main__":
    main()
