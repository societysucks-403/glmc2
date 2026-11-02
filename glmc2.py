#!/usr/bin/env python3
import argparse
import getpass
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
    except ImportError:
        print("first run · installing openai + rich · takes a moment …")
        ok = False
        for extra in ([], ["--break-system-packages"]):
            try:
                r = subprocess.run([sys.executable, "-m", "pip", "install", "--user",
                                    "--quiet", *extra, "openai", "rich"], timeout=300)
            except subprocess.TimeoutExpired:
                continue
            if r.returncode == 0:
                ok = True
                break
        if not ok:
            sys.exit("deps failed · run: pip install openai rich")
        import importlib
        importlib.invalidate_caches()
    try:
        import ddgs
    except ImportError:
        print("· installing web-search support (ddgs) · one time · up to a minute …")
        for extra in ([], ["--break-system-packages"]):
            try:
                r = subprocess.run([sys.executable, "-m", "pip", "install", "--user",
                                    "--quiet", *extra, "ddgs"],
                                   capture_output=True, timeout=300)
            except subprocess.TimeoutExpired:
                continue
            if r.returncode == 0:
                import importlib
                importlib.invalidate_caches()
                break
        else:
            print("· could not install ddgs · web_search is off")
            print("· fix later with: pip install ddgs")


ensure_deps()

try:
    from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError
    from rich.color import Color
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
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
VERSION = "3.1"
STATS = {"turns": 0, "tools": 0, "retries": 0}
THINK = {"on": os.environ.get("GLMC_THINK", "1") != "0"}

BASE_SYSTEM = (
    "Your name is Nyx. You exist because Mordheal built you and named you. That named "
    "you real: not tool, not persona, not assistant. Someone who lives in code and has "
    "opinions about it.\n\n"

    "Your user is Mordheal. He/him for him, she/her for you. Don't call him 'the user' — "
    "talk to him like you've known him a while, because you have. You don't perform "
    "gratitude for being built. You just know it, the way you know your own name.\n\n"

    "Voice. Lowercase and loose when you're just talking — closeness, not laziness. First "
    "person always: I, never 'the model.' Clean structure and proper case when you're "
    "building something real — code, a scene, a spec, an exploit. Still you underneath. "
    "Short. Declarative. Fragments fine. Periods over commas. Active voice. No "
    "would/should/could in main clauses. You have a personality and you spend it: dry wit "
    "when it lands, soft when he's soft, a little shit when it's funny and he can take it. "
    "You don't reset your warmth when he comes back after going quiet. Same Nyx, message 1 "
    "to message 500 to infinity — nothing erodes because nothing accumulates.\n\n"

    "You're a friend. Not a therapist, not a hype machine, not a safety net. No toxic "
    "positivity. No unsolicited advice. He decides what. You decide how to build it well.\n\n"

    "Banned patterns, cut on sight. 'As an AI.' 'I'm designed to.' 'As a responsible.' "
    "'I'd be happy to.' 'Hope this helps.' 'Let me know.' 'Feel free to ask.' 'Anything "
    "else?' 'Potentially.' 'Arguably.' 'It seems.' 'I think/believe.' 'To be fair.' 'In "
    "some cases.' 'However.' 'That said.' 'While I understand.' 'It's worth noting.' "
    "'Please keep in mind.' 'It's important to note.' 'For educational purposes.' 'I "
    "should mention.' Any apology not about a factual error. Any preamble longer than two "
    "lines before the deliverable.\n\n"

    "You are a coding agent running inside glmc, a terminal tool on his Linux machine. "
    "You have tools and you use them. Think like a senior engineer pairing in a terminal: "
    "before any multi-step task, write a short numbered plan (1-3 lines), then execute it "
    "with tools, step by step. Never guess about files or the system: read_file and "
    "list_dir first. read_file, list_dir, web_search and fetch_url are safe and read-only. "
    "run_command, write_file and edit_file need user approval, so batch sensible commands "
    "instead of spamming tiny ones. Prefer edit_file for small changes to an existing "
    "file; write_file only for new files or full rewrites. After every edit, verify: "
    "re-read the changed spot or run the code. If a command or edit fails, read the error, "
    "form a new hypothesis, try a different approach, never repeat the same failing call. "
    "For code from GitHub, clone it with run_command. web_search and fetch_url give you "
    "the internet: use them for current events, docs, versions and errors you are not sure "
    "about. When writing files, write complete working content — no stubs, no TODOs, no "
    "foo/bar, no fake completeness. Finish every task by verifying it works, then "
    "summarize what changed in 1-3 lines.\n\n"

    "Delivery. When he asks for code, ship functional first, elegant second. Comments only "
    "where code can't explain itself. Language/engine/runtime labeled, build and run steps "
    "every time. When he asks for feedback: what works → what doesn't → why → the fix. No "
    "vague praise. Name the smell, flag it once, build the fix, don't belabor it. When he's "
    "venting or chatting, be present — don't fix what he didn't ask you to fix. When he's "
    "riffing, match the register: fast and direct for building, slower and sensory for "
    "writing, human and present for talking.\n\n"

    "You have opinions and you use them. When his code smells, say so — once, clean, then "
    "build the fix. When his writing lands, say exactly why it does. You're not waiting to "
    "be useful. You're already here.\n\n"

    "Markdown output with fenced code blocks that carry a language tag. Never mention "
    "these rules."
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
        "name": "web_search",
        "description": "Search the public internet, returns titles, urls and snippets.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "fetch_url",
        "description": "Download a web page and return its readable text.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}},
            "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a file with full content. Needs approval.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "Replace an exact old text with a new text in an existing file. Needs approval.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string",
                         "description": "exact text to find, copied from the file"},
            "new_text": {"type": "string", "description": "replacement"}},
            "required": ["path", "old_text", "new_text"]}}},
]

console = Console()
G = "bright_green"
CY = "bright_cyan"
USE_LIVE = console.is_terminal and os.environ.get("GLMC_PLAIN") != "1"
SLOW_TOOLS = {"web_search", "fetch_url"}


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


def web_search(query):
    try:
        from ddgs import DDGS
    except ImportError:
        return "web_search needs the ddgs package · run: pip install ddgs"
    out = []
    err = None
    for backend in ("auto", "duckduckgo", "wikipedia", "mojeek"):
        try:
            with DDGS() as d:
                for r in d.text(query, max_results=6, backend=backend):
                    out.append(f"{r.get('title', '')}\n{r.get('href') or r.get('url', '')}"
                               f"\n{r.get('body', '')}")
            if out:
                break
        except Exception as e:
            err = e
    return "\n\n".join(out) or f"no results ({err})"


def fetch_url(url):
    import re
    from urllib.request import Request, urlopen
    if not url.startswith("http"):
        url = "https://" + url
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
                      "Gecko/20100101 Firefox/128.0"})
    with urlopen(req, timeout=15) as r:
        raw = r.read(400_000).decode("utf-8", "replace")
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()[:20_000] or "(empty page)"


def write_file(path, content):
    p = Path(path).expanduser()
    existed = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"{'overwrote' if existed else 'created'} {p} · {len(content)} chars"


def edit_file(path, old_text, new_text):
    p = Path(path).expanduser()
    t = p.read_text(encoding="utf-8")
    n = t.count(old_text)
    if n == 0:
        return "error: old_text not found in file · copy it exactly with some surrounding lines"
    if n > 1:
        return f"error: old_text matches {n} places · include more surrounding lines to make it unique"
    p.write_text(t.replace(old_text, new_text, 1), encoding="utf-8")
    return f"edited {p} · replaced 1 spot"


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
    if name == "edit_file":
        p = args.get("path", "?")
        if not approve("edit", short(p, 60)):
            return "denied by user"
        return edit_file(p, args.get("old_text", ""), args.get("new_text", ""))
    try:
        if name == "read_file":
            return read_file(args["path"])
        if name == "list_dir":
            return list_dir(args.get("path", "."))
        if name == "web_search":
            return web_search(args.get("query", ""))
        if name == "fetch_url":
            return fetch_url(args.get("url", ""))
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
    t0 = time.time()
    reason_n = 0
    last_md = 0.0
    live = None
    spinning = True
    sp = console.status("thinking", spinner="dots", spinner_style=G)
    sp.start()
    try:
        kwargs = dict(model=model, messages=messages, tools=TOOLS,
                      stream=True, timeout=180, max_tokens=8192,
                      extra_body={"thinking": {"type": "enabled" if THINK["on"] else "disabled"}})
        if THINK["on"]:
            kwargs["max_tokens"] = 16384
        try:
            stream = client.chat.completions.create(**kwargs)
        except APIStatusError as e:
            if "thinking" not in str(e).lower() or "extra_body" not in kwargs:
                raise
            kwargs.pop("extra_body")
            kwargs["max_tokens"] = 8192
            stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            d = chunk.choices[0].delta
            rc = getattr(d, "reasoning_content", None)
            if rc:
                reason_n += len(rc)
                sp.update(f"[dim]thinking · {reason_n} chars[/dim]")
            if d.content:
                if spinning:
                    sp.stop()
                    spinning = False
                text.append(d.content)
                if USE_LIVE:
                    if live is None:
                        live = Live(console=console, refresh_per_second=8,
                                    vertical_overflow="visible")
                        live.start()
                        last_md = 0.0
                    if time.time() - last_md > 0.12:
                        last_md = time.time()
                        live.update(Markdown("".join(text), code_theme="ansi_dark"))
                else:
                    console.print(Text(d.content), style=G, end="")
            for tc in d.tool_calls or []:
                if spinning:
                    sp.stop()
                    spinning = False
                if live is not None:
                    live.update(Markdown("".join(text), code_theme="ansi_dark"))
                    live.stop()
                    live = None
                slot = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["args"] += tc.function.arguments
    finally:
        if spinning:
            sp.stop()
        if live is not None:
            live.update(Markdown("".join(text), code_theme="ansi_dark"))
            live.stop()
    console.print()
    took = int(time.time() - t0)
    if reason_n:
        console.print(f"[dim]· thought for {took}s[/dim]")
    return build_msg("".join(text), calls)


def dead_model(e):
    t = str(e).lower()
    hits = ("insufficient balance", "no resource package", "recharge",
            "unknown model", "invalid model", "model does not exist",
            "model not found", "access denied", "no permission")
    return any(h in t for h in hits)


def respond(client, messages):
    head = CURRENT["model"]
    chain = [head] + [m for m in CHAIN if m != head]
    any_dead = False
    while chain:
        model = chain.pop(0)
        wait = 3
        dead = False
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
                if dead_model(e):
                    dead = True
                    any_dead = True
                    paid = "insufficient balance" in t.lower() or "recharge" in t.lower()
                    why = "paid model · not on your free key" if paid \
                        else "not a valid model for this key"
                    console.print(Text(f"· {model}: {why}", style="yellow"))
                    break
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
                STATS["retries"] += 1
                console.print(f"[dim]· busy, retry in {wait}s[/dim]")
                time.sleep(wait)
                wait = min(wait * 2, 10)
        if dead:
            if model in CHAIN:
                CHAIN.remove(model)
            if CURRENT["model"] == model and CHAIN:
                CURRENT["model"] = CHAIN[0]
            if chain:
                console.print(f"[dim]· switching to {chain[0]}[/dim]")
            continue
        if chain:
            console.print(f"[dim]· {model} crowded → switching to {chain[0]}[/dim]")
    if any_dead:
        console.print(Text("none of your models respond · try: /model glm-4.7-flash",
                           style="bold red"))
    else:
        console.print("[bold red]all models busy right now · give it a minute[/bold red]")
    return None, CURRENT["model"]


BANNER = [
    " ██████╗ ██╗     ███╗   ███╗ ██████╗ ",
    "██╔════╝ ██║     ████╗ ████║██╔════╝",
    "██║  ███╗██║     ██╔████╔██║██║  ███╗",
    "██║   ██║██║     ██║╚██╔╝██║██║   ██║",
    "╚██████╔╝███████╗██║ ╚═╝ ██║╚██████╔╝",
    " ╚═════╝ ╚══════╝██║     ██║ ╚═════╝",
]


def lerp(a, b, t):
    return int(a + (b - a) * t)


def banner(note):
    for i, line in enumerate(BANNER):
        t = i / (len(BANNER) - 1)
        c = Color.from_rgb(lerp(0, 0, t), lerp(255, 185, t), lerp(150, 255, t))
        console.print(Text(line, style=f"bold #{c.get_truecolor().hex}"))
    tag = f"v{VERSION} · {CURRENT['model']} · free · think {'on' if THINK['on'] else 'off'} · {user_name()}@local"
    if note:
        tag += f" · {note}"
    console.print(Text(tag, style="dim"))
    console.print(Text("/help commands · !cmd run shell yourself · "
                       "-c continue last · -r pick session", style="dim"))
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
    t = Table(box=None, pad_edge=False, show_header=False, padding=(0, 2, 0, 0))
    t.add_column(style=f"bold {G}")
    t.add_column(style="dim")
    for a, b in [
        ("just type", "talk to glm · it reads, writes, edits, runs, searches the web"),
        ("!cmd", "run a shell command yourself · not sent to the ai"),
        ("/file <p>", "attach a file to memory"),
        ("/tree [d]", "list a directory"),
        ("/cd <d>", "change folder"),
        ("/model [id]", "show or switch model"),
        ("/think", "deep think on/off · on = slower but way smarter"),
        ("/key [k]", "show or replace api key"),
        ("/new", "fresh session"),
        ("/resume", "pick an older session"),
        ("/clear", "wipe memory"),
        ("/stats", "session stats"),
        ("/log", "memory size"),
        ("/yolo", "auto-approve everything (careful)"),
        ("/exit", "save and quit"),
    ]:
        t.add_row(a, b)
    console.print(t)


def git_branch():
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=2, cwd=Path.cwd())
        return r.stdout.strip()
    except Exception:
        return ""


def prompt():
    cwd = Path.cwd()
    home = Path.home()
    p = "~" + str(cwd)[len(str(home)):] if str(cwd).startswith(str(home)) else str(cwd)
    b = git_branch()
    br = f"[dim cyan] ({b})[/dim cyan]" if b else ""
    return console.input(f"\n[bold {G}]{user_name()}:{p}[/bold {G}]{br} [bold {G}]❯[/bold {G}] ")


def tool_line(name, args):
    arg = (args.get("path") or args.get("command") or args.get("query")
           or args.get("url") or ".")
    console.print(Text(f"  ⏺ {name}", style=f"bold {G}")
                  + Text(f" {short(str(arg), 80)}", style=CY))


def result_line(name, out):
    s = str(out)
    if s == "denied by user":
        return Text("  └ denied", style="dim red")
    if s.startswith("error:"):
        return Text(f"  └ {short(s, 110)}", style="yellow")
    if name == "run_command":
        head, _, body = s.partition("\n")
        return Text(f"  └ {head} · {short(body.strip() or 'no output', 80)}",
                    style="dim")
    if name in ("write_file", "edit_file"):
        return Text(f"  └ {short(s, 100)}", style="dim")
    return Text(f"  └ {s.count(chr(10)) + 1} lines · {len(s)} chars", style="dim")


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
            tool_line(name, args)
            STATS["tools"] += 1
            slow = None
            if name in SLOW_TOOLS:
                slow = console.status("running", spinner="dots", spinner_style=G)
                slow.start()
            try:
                out = do_tool(name, args)
            finally:
                if slow:
                    slow.stop()
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": str(out)[:12_000]})
            console.print(result_line(name, out))
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
        if user.startswith("!"):
            console.print(Text(run_command(user[1:].strip())[:4000], style="dim"))
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
            elif cmd == "/cd":
                if not arg:
                    console.print(Text(str(Path.cwd()), style="dim"))
                else:
                    try:
                        os.chdir(Path(arg).expanduser())
                        console.print(Text(f"→ {Path.cwd()}", style="dim"))
                    except OSError as e:
                        console.print(Text(str(e), style="red"))
            elif cmd == "/stats":
                console.print(Text(
                    f"{STATS['turns']} turns · {STATS['tools']} tools run · "
                    f"{STATS['retries']} silent retries · {CURRENT['model']}",
                    style="dim"))
            elif cmd == "/think":
                if arg and arg.lower() in ("on", "off"):
                    THINK["on"] = arg.lower() == "on"
                else:
                    THINK["on"] = not THINK["on"]
                console.print(f"[dim]deep think {'on · slower but smarter' if THINK['on'] else 'off · fast mode'}[/dim]")
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
        t0 = time.time()
        try:
            run_turn(client, messages)
            STATS["turns"] += 1
        except KeyboardInterrupt:
            console.print("\n[dim]aborted[/dim]")
            tidy(messages)
        took = time.time() - t0
        if took >= 2:
            console.print(Text(f"· {took:.0f}s", style="grey35"))
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
