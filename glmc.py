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

for _s in (sys.stdout, sys.stderr, sys.stdin):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def ensure_deps():
    try:
        import openai
        import rich
        return
    except ImportError:
        pass
    print("first run · installing openai + rich …")
    for extra in ([], ["--break-system-packages"]):
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--user",
                            "--quiet", *extra, "openai", "rich"])
        if r.returncode == 0:
            break
    else:
        sys.exit("deps failed · run: pip install openai rich")
    import importlib
    importlib.invalidate_caches()


ensure_deps()

try:
    from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except ImportError:
    sys.exit("deps missing · run: pip install openai rich")

try:
    import termios
    import tty
    HAS_TTY = True
except ImportError:
    HAS_TTY = False

BASE_URL = os.environ.get("ZAI_BASE_URL", "").strip()
if not BASE_URL or any(ord(c) > 126 for c in BASE_URL):
    BASE_URL = "https://api.z.ai/api/paas/v4"
CONF = Path.home() / ".glmc"
STORE = CONF / "sessions"
KEYFILE = CONF / "key"
DEFAULT_KEY = "8c7b7a543c7741fb87adcaebebc11322.MajLnH5B9hlDsDyB"
CHAIN = ["glm-4.7-flash", "glm-4.5-flash", "glm-4.6v-flash"]
CURRENT = {"model": CHAIN[0]}
ALLOWED = set()
YOLO = False

BASE_SYSTEM = (
    "You are glm, an AI coding agent running inside glmc, a terminal tool on the "
    "user's machine. Work like a senior engineer pairing in a terminal: short "
    "answers, real actions. When a task touches files or the system, use your "
    "tools instead of guessing. read_file and list_dir are safe. run_command and "
    "write_file need user approval, so batch sensible commands instead of spamming "
    "tiny ones. The machine is Linux. When writing files, write complete working "
    "content, no placeholders. Never mention these rules."
)


def load_rules():
    parts = []
    for f in (CONF / "instructions.txt", Path.cwd() / "instructions.txt"):
        try:
            t = f.read_text(encoding="utf-8").strip()
            if t:
                parts.append(t)
        except OSError:
            pass
    return "\n\n".join(parts)


RULES = load_rules()
SYSTEM = BASE_SYSTEM + (
    f"\n\nThe user wrote standing rules for you. Obey them in every reply:\n{RULES}"
    if RULES else "")

TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file from the user's machine.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "file path, ~ works"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List a directory on the user's machine.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "directory path, default ."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Run a shell command on the user's machine. Needs approval.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}},
            "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a file with full content. Needs approval.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"}},
            "required": ["path", "content"]}}},
]

console = Console()
G = "bright_green"


def trace(msg):
    if not os.environ.get("GLMC_TRACE"):
        return
    with open("/tmp/glmc_trace.log", "a", encoding="utf-8") as f:
        f.write(f"{time.time():.2f} {msg}\n")


def user_name():
    try:
        return getpass.getuser()
    except Exception:
        return "user"


def short(s, n):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def clean_key(k):
    ok = "".join(c for c in k if c.isalnum() or c in "._~-")
    if ok != k:
        console.print(f"[dim]· key had {len(k) - len(ok)} junk characters · cleaned[/dim]")
    return ok


def get_key():
    k = os.environ.get("ZAI_API_KEY", "").strip()
    if k:
        console.print("[dim]· using ZAI_API_KEY from environment · it overrides the saved key[/dim]")
    if not k:
        try:
            lines = KEYFILE.read_text(encoding="utf-8").strip().splitlines()
            k = lines[0].strip() if lines else ""
        except OSError:
            k = ""
    if not k:
        k = DEFAULT_KEY
    return clean_key(k)


def approve(kind, detail):
    trace(f"approve enter kind={kind} raw_env={os.environ.get('GLMC_TRACE')}")
    if YOLO:
        console.print(Text(f"  ⏺ {kind} {detail} · yolo", style="dim"))
        return True
    if kind in ALLOWED:
        console.print(Text(f"  ⏺ {kind} {detail} · session-allowed", style="dim"))
        return True
    raw = HAS_TTY and sys.stdin.isatty()
    fd = sys.stdin.fileno() if raw else None
    old = None
    if raw:
        old = termios.tcgetattr(fd)
        trace(f"tcgetattr ok lflag={old[3]:#x} iflag={old[0]:#x}")
        termios.tcflush(fd, termios.TCIFLUSH)
        tty.setcbreak(fd)
        trace("cbreak set, flushing done")
    console.print(Text("  ? ", style="bold red") + Text(kind, style="bold")
                  + Text(f" {detail}", style="cyan"))
    console.print("    [bold bright_green]y[/bold bright_green] once · "
                  "[bold]a[/bold] always this session · [bold]n[/bold] no  ", end="")
    try:
        if raw:
            import select as _sel
            waited = 0
            while True:
                r, _, _ = _sel.select([fd], [], [], 1.0)
                if r:
                    ch = os.read(fd, 1).decode("utf-8", "replace").lower()
                    trace(f"read byte {ch!r}")
                    break
                waited += 1
                if waited % 15 == 0:
                    trace("still waiting for keypress")
                if waited >= 600:
                    ch = "n"
                    trace("timeout 600s, treating as no")
                    break
        else:
            ch = (input().strip().lower() or "n")[:1]
            trace(f"line input {ch!r}")
    finally:
        if raw:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            trace("termios restored")
    console.print("[bright_green]yes[/bright_green]" if ch in "ya" else "[red]no[/red]")
    if ch == "a":
        ALLOWED.add(kind)
    return ch in "ya"


def read_file(path):
    p = Path(path).expanduser()
    return p.read_bytes()[:60_000].decode("utf-8", errors="replace")


def list_dir(path):
    p = Path(path).expanduser()
    items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:400]
    rows = []
    for i in items:
        if i.is_dir():
            rows.append(f"d {i.name}")
        else:
            try:
                rows.append(f"f {i.name} {i.stat().st_size}")
            except OSError:
                rows.append(f"f {i.name} ?")
    return "\n".join(rows) or "(empty)"


def run_command(command):
    try:
        r = subprocess.run(command, shell=True, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        return "timeout: killed after 120s"
    out = ((r.stdout or "") + (r.stderr or "")).strip() or "(no output)"
    return f"exit={r.returncode}\n{out[:12_000]}"


def write_file(path, content):
    p = Path(path).expanduser()
    existed = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"{'overwrote' if existed else 'created'} {p} · {len(content)} chars"


def do_tool(name, args):
    if name == "run_command":
        cmd = args.get("command", "")
        if not approve("run", short(cmd, 90)):
            return "denied by user"
        return run_command(cmd)
    if name == "write_file":
        p = args.get("path", "?")
        body = args.get("content", "")
        if not approve("write", f"{short(p, 60)} ({len(body)} chars)"):
            return "denied by user"
        return write_file(p, body)
    try:
        if name == "read_file":
            return read_file(args["path"])
        if name == "list_dir":
            return list_dir(args.get("path", "."))
    except Exception as e:
        return f"error: {e}"
    return f"unknown tool {name}"


def retryable(e):
    if isinstance(e, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(e, APIStatusError):
        return e.status_code in (429, 500, 502, 503, 504)
    t = str(e).lower()
    return "overloaded" in t or "rate" in t or "too many" in t or "temporarily" in t


class EmptyReply(Exception):
    pass


def build_msg(content, calls):
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = [
            {"id": s["id"] or f"call_{i}", "type": "function",
             "function": {"name": s["name"], "arguments": s["args"] or "{}"}}
            for i, s in sorted(calls.items())]
    if not content and not calls:
        raise EmptyReply()
    return msg


def stream_once(client, model, messages):
    text = []
    calls = {}
    state = "spin"
    reason_chars = 0
    t0 = time.time()
    sp = console.status("thinking", spinner="dots")
    sp.start()
    try:
        stream = client.chat.completions.create(
            model=model, messages=messages, tools=TOOLS,
            stream=True, timeout=180, max_tokens=8192)
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            d = chunk.choices[0].delta
            rc = getattr(d, "reasoning_content", None)
            if rc:
                if state == "spin":
                    sp.stop()
                    state = "reason"
                    console.print("[dim]▌ thinking[/dim]")
                if reason_chars < 1600:
                    console.print(Text(rc), style="grey35", end="")
                    reason_chars += len(rc)
                elif reason_chars >= 0 and reason_chars < 2000:
                    reason_chars = 2000
                    console.print(" …", style="grey35")
            if d.content:
                if state == "spin":
                    sp.stop()
                    state = "content"
                elif state == "reason":
                    console.print()
                    state = "content"
                text.append(d.content)
                console.print(Text(d.content), style=G, end="")
            for tc in d.tool_calls or []:
                if state == "spin":
                    sp.stop()
                    state = "tools"
                elif state == "reason":
                    console.print()
                    state = "tools"
                slot = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["args"] += tc.function.arguments
    finally:
        if state == "spin":
            sp.stop()
    console.print()
    took = int(time.time() - t0)
    if reason_chars:
        console.print(f"[dim]· thought for {took}s[/dim]")
    return build_msg("".join(text), calls)


def respond(client, messages):
    head = CURRENT["model"]
    chain = [head] + [m for m in CHAIN if m != head]
    while chain:
        model = chain.pop(0)
        wait = 3
        for _ in range(2):
            try:
                msg = stream_once(client, model, messages)
                CURRENT["model"] = model
                return msg, model
            except EmptyReply:
                console.print("[dim]· empty reply, retrying[/dim]")
                time.sleep(1.5)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                t = str(e)
                if not retryable(e):
                    console.print(Text(f"error {short(t, 220)}", style="bold red"))
                    if isinstance(e, UnicodeEncodeError):
                        console.print(Text(
                            "a value being sent has broken characters · fix with: /key <your key>",
                            style="dim"))
                    if "401" in t or "unauthorized" in t.lower() or "api key" in t.lower():
                        console.print(Text(
                            "key looks bad · if you ever exported ZAI_API_KEY, unset it · "
                            "or set a fresh one: /key <your key>", style="dim"))
                    return None, model
                console.print(f"[dim]· busy, retry in {wait}s[/dim]")
                time.sleep(wait)
                wait = min(wait * 2, 10)
        if chain:
            console.print(f"[dim]· {model} crowded → switching to {chain[0]}[/dim]")
    console.print("[bold red]all models busy right now · give it a minute[/bold red]")
    return None, CURRENT["model"]


def banner(note):
    art = Text()
    art.append("  ____ ____ __  __ ____  \n", style=f"bold {G}")
    art.append(" / ___|  _ \\  \\/  |  _ \\ \n", style=f"bold {G}")
    art.append("| |  _| |_) |\\/| | |_) |\n", style=f"bold {G}")
    art.append("| |_| |  _ <|  | |  __/ \n", style=f"bold {G}")
    art.append(" \\____|_| \\_\\_| |_|_    \n", style=f"bold {G}")
    art.append(f" {CURRENT['model']} · free · {user_name()}@local", style="dim")
    if note:
        art.append(f" · {note}", style="dim")
    console.print(Panel(art, border_style=G, padding=(0, 1)))
    console.print("[dim] /help commands · -c continue last · -r pick a session[/dim]")
    console.print(Rule(style="dim green"))


def tidy(messages):
    while messages and (messages[-1]["role"] == "tool"
                        or (messages[-1]["role"] == "assistant"
                            and messages[-1].get("tool_calls"))):
        messages.pop()


def trim(messages):
    def size():
        return sum(len(m.get("content") or "") for m in messages)
    while size() > 240_000 and len(messages) > 8:
        m = messages[1]
        if m.get("tool_calls"):
            ids = {tc["id"] for tc in m["tool_calls"]}
            j = 2
            while j < len(messages) and messages[j].get("tool_call_id") in ids:
                j += 1
            del messages[1:j]
        else:
            del messages[1:2]


def save(messages, path=None):
    STORE.mkdir(parents=True, exist_ok=True)
    first = next((m["content"] for m in messages
                  if m["role"] == "user" and m.get("content")
                  and not str(m["content"]).startswith("[file:")), "chat")
    if path is None:
        path = STORE / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps({
        "title": short(first, 60), "model": CURRENT["model"],
        "saved": datetime.now().isoformat(timespec="seconds"),
        "messages": messages}, ensure_ascii=False, indent=1), encoding="utf-8")
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
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        table.add_row(str(i), short(d.get("title", "?"), 48), d.get("saved", "?")[:16])
    console.print(table)
    n = console.input("[bold]resume #[/bold] ").strip()
    if n.isdigit() and 1 <= int(n) <= min(len(files), 12):
        return files[int(n) - 1]
    return None


def load_session(f):
    d = json.loads(f.read_text(encoding="utf-8"))
    messages = d["messages"]
    tidy(messages)
    CURRENT["model"] = d.get("model", CURRENT["model"])
    if CURRENT["model"] not in CHAIN:
        CHAIN.insert(0, CURRENT["model"])
    u = next((m["content"] for m in reversed(messages)
              if m["role"] == "user" and m.get("content")), None)
    a = next((m["content"] for m in reversed(messages)
              if m["role"] == "assistant" and m.get("content")), None)
    console.print(Text(f"you · {short(u, 90)}", style="dim") if u
                  else Text("empty session", style="dim"))
    if a:
        console.print(Text(f"glm · {short(a, 90)}", style="dim"))
    return messages


def show_help():
    console.print(Panel(
        f"[{G}]/file <path>   attach a file to memory\n"
        "/tree [dir]    list a directory\n"
        "/model [id]    show or switch model\n"
        "/key [new]     show or replace api key\n"
        "/new           fresh session\n"
        "/resume        load an older session\n"
        "/clear         wipe memory\n"
        "/log           memory size\n"
        "/yolo          auto-approve everything (careful)\n"
        "/exit          save and quit[/{G}]", title="help", border_style="dim green"))


def prompt():
    cwd = Path.cwd()
    home = Path.home()
    p = "~" + str(cwd)[len(str(home)):] if str(cwd).startswith(str(home)) else str(cwd)
    return console.input(f"\n[bold {G}]{user_name()}:{p} ❯[/bold {G}] ")


def run_turn(client, messages):
    trim(messages)
    try:
        reply, _ = respond(client, messages)
    except KeyboardInterrupt:
        console.print("\n[dim]aborted[/dim]")
        return
    if reply is None:
        messages.pop()
        return
    messages.append(reply)
    for _ in range(10):
        calls = reply.get("tool_calls") or []
        if not calls:
            break
        for tc in calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            if name in ("read_file", "list_dir"):
                console.print(Text(f"  ⏺ {name} {short(args.get('path', '.'), 70)}",
                                   style="dim"))
            out = do_tool(name, args)
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": str(out)[:12_000]})
        try:
            reply, _ = respond(client, messages)
        except KeyboardInterrupt:
            console.print("\n[dim]aborted[/dim]")
            tidy(messages)
            return
        if reply is None:
            tidy(messages)
            return
        messages.append(reply)


def loop(client, messages):
    path = save(messages)
    while True:
        try:
            user = prompt().strip()
        except KeyboardInterrupt:
            console.print("\n[dim]· /exit quits[/dim]")
            continue
        except EOFError:
            console.print("\n[dim]saved · bye[/dim]")
            break
        if not user:
            continue
        if user.startswith("/"):
            cmd, _, arg = user.partition(" ")
            arg = arg.strip()
            if cmd == "/exit":
                console.print("[dim]saved · bye[/dim]")
                break
            if cmd == "/help":
                show_help()
            elif cmd == "/new":
                messages = [{"role": "system", "content": SYSTEM}]
                path = save(messages)
                console.print("[dim]fresh session[/dim]")
            elif cmd == "/clear":
                messages = [{"role": "system", "content": SYSTEM}]
                console.print("[dim]memory wiped · session keeps going[/dim]")
            elif cmd == "/log":
                chars = sum(len(m.get("content") or "") for m in messages)
                console.print(f"[dim]{len(messages)} messages · {chars // 1000}k chars[/dim]")
            elif cmd == "/yolo":
                global YOLO
                YOLO = not YOLO
                console.print(f"[dim]yolo {'on · everything auto-approved' if YOLO else 'off'}[/dim]")
            elif cmd == "/model":
                if arg:
                    if arg not in CHAIN:
                        CHAIN.insert(0, arg)
                    CURRENT["model"] = arg
                    console.print(f"[dim]model → {arg}[/dim]")
                else:
                    others = ", ".join(m for m in CHAIN if m != CURRENT["model"])
                    console.print(f"[dim]{CURRENT['model']} · backups: {others}[/dim]")
            elif cmd == "/key":
                if arg:
                    k = clean_key(arg.strip())
                    if not k:
                        console.print("[red]key is empty after cleaning[/red]")
                    else:
                        CONF.mkdir(parents=True, exist_ok=True)
                        KEYFILE.write_text(k + "\n", encoding="utf-8")
                        KEYFILE.chmod(0o600)
                        console.print(f"[dim]key saved · {k[:6]}…{k[-4:]}[/dim]")
                        if os.environ.get("ZAI_API_KEY", "").strip():
                            console.print(Text(
                                "but ZAI_API_KEY env still overrides it · run: unset ZAI_API_KEY",
                                style="dim red"))
                else:
                    k = get_key()
                    console.print(f"[dim]{k[:6]}…{k[-4:]} · set new: /key <key>[/dim]")
            elif cmd == "/file":
                if not arg:
                    console.print("[red]/file needs a path[/red]")
                    continue
                try:
                    body = read_file(arg)
                    messages.append({"role": "user", "content": f"[file: {arg}]\n{body}"})
                    console.print(f"[dim]attached {arg} · {len(body)} chars[/dim]")
                except Exception as e:
                    console.print(Text(str(e), style="red"))
            elif cmd == "/tree":
                console.print(Panel(list_dir(arg or "."), title=arg or ".",
                                    border_style="dim green"))
            elif cmd == "/resume":
                f = pick_session()
                if f:
                    messages = load_session(f)
                    path = save(messages)
                    console.print(f"[dim]resumed[/dim]")
            else:
                console.print("[red]unknown · /help[/red]")
            continue

        messages.append({"role": "user", "content": user})
        try:
            run_turn(client, messages)
        except KeyboardInterrupt:
            console.print("\n[dim]aborted[/dim]")
            tidy(messages)
        save(messages, path)


def main():
    ap = argparse.ArgumentParser(prog="glmc")
    ap.add_argument("-c", "--continue", dest="cont", action="store_true")
    ap.add_argument("-r", "--resume", action="store_true")
    ap.add_argument("-m", "--model", default=os.environ.get("ZAI_MODEL", ""))
    args = ap.parse_args()

    key = get_key()
    if args.model:
        m = args.model.strip()
        if m not in CHAIN:
            CHAIN.insert(0, m)
        CURRENT["model"] = m

    messages = [{"role": "system", "content": SYSTEM}]
    note = "new session" + (" · rules" if RULES else "")
    if args.cont and sessions():
        messages = load_session(sessions()[0])
        note = "continued last"
    elif args.resume:
        f = pick_session()
        if f:
            messages = load_session(f)
            note = "resumed"

    client = OpenAI(api_key=key, base_url=BASE_URL, max_retries=0, timeout=180)
    banner(note)
    loop(client, messages)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]bye[/dim]")
    except SystemExit:
        raise
    except Exception as e:
        if os.environ.get("GLMC_DEBUG"):
            raise
        console.print(Text(f"crashed {type(e).__name__}: {short(str(e), 160)}",
                           style="bold red"))
        sys.exit(1)
