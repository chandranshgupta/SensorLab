"""launcher - the interactive control panel behind run.bat and run.sh (prime directive P8).

Standard library only, Python 3.9+, Windows, macOS and Linux. run.bat / run.sh find Python and
build .venv, then start this file with the .venv interpreter:

    run.bat                 arrow-key menu        (run.sh on macOS/Linux)
    run.bat run [args]      run the app            run.bat trace [args]   line-level trace + report
    run.bat test [--all|--live]                    run.bat diagnose       preflight only
    run.bat report          latest trace summary   run.bat repair         reinstall dependencies
    run.bat ports           who uses the app port  run.bat logs           recent launcher logs
    flags: --plain (no colour, ASCII)   --yes (never prompt; for agents and CI)

Menu keys: Up/Down or j/k move, Enter runs, 1-9 jump and run, q or Esc quits.
Scripted input for automated tests: LAUNCHER_KEYS="down,down,enter,q".

Every action gets a run id (APP_RUN_ID); it names logs/launcher/<id>.log and the trace file
logs/trace/<id>.jsonl, so a result can always be traced back to the run that produced it.
Never changes system settings, never installs globally, never downloads tools unasked.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path

# ---- project settings (sirf yeh hissa edit karo) ------------------------------
APP_NAME = "SensorLab"
APP_KIND = "module"                 # "module": python -m APP_MODULE chalega   "server": python SERVER_ARGS chalega
APP_MODULE = "simulator.main"       # default entry module jab tak server ready na ho
PORT = int(os.environ.get("PORT") or (Path("port.txt").read_text().strip() if Path("port.txt").exists() else 8080))
SERVER_ARGS = ["-m", "http.server", str(PORT)]
APP_URL = f"http://127.0.0.1:{PORT}"
OPEN_BROWSER = False
PY_MIN = (3, 10)
PROBE_IMPORTS: list[str] = []       # external dependencies yahan list karein
REQUIREMENTS = "requirements.txt"   # dependency manifest file
DATA_DIRS = ["logs", "data"]
TRACE_KIT = "simulator/trace_kit.py"
PREFLIGHT = "preflight.py"
TEST_LIVE_MARKER = "live"
# Project ke custom actions: (naam, label, description, interpreter ke baad ke argv)
EXTRA_ACTIONS: list[tuple[str, str, str, list[str]]] = []
# ------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):  # hamari lines aur child process ka output sahi order mein rahein
        _stream.reconfigure(line_buffering=True)
PY = sys.executable
SESSION = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
LOG_DIR = ROOT / "logs" / "launcher"
PLAIN = "--plain" in sys.argv or bool(os.environ.get("NO_COLOR"))
AUTO = "--yes" in sys.argv
ARGS = [a for a in sys.argv[1:] if a not in ("--plain", "--yes", "--rebuild")]
IS_WIN = os.name == "nt"


# ------------------------------------------------------------------ terminal
def _enable_vt() -> bool:
    """Sirf is console ke liye ANSI colours on karo (registry ko haath nahi lagate)."""
    if not IS_WIN:
        return True
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except (AttributeError, OSError):
        return False


COLOR = not PLAIN and sys.stdout.isatty() and _enable_vt()
UNICODE = not PLAIN and (sys.stdout.encoding or "").lower().replace("-", "") in ("utf8", "utf8sig")


def c(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if COLOR else text


CYAN, GREEN, GOLD, RED, GRAY, BOLD, INV = ("38;2;56;189;248", "38;2;52;211;153", "38;2;251;191;36",
                                          "38;2;248;113;113", "38;2;148;163;184", "1", "7")
BOX = dict(tl="╭", tr="╮", bl="╰", br="╯", h="─", v="│", ml="├", mr="┤", arrow="❯", dot="·") if UNICODE \
    else dict(tl="+", tr="+", bl="+", br="+", h="-", v="|", ml="+", mr="+", arrow=">", dot="-")


def width() -> int:
    return max(60, min(shutil.get_terminal_size((88, 24)).columns, 100))


def visible_len(s: str) -> int:
    import re
    return len(re.sub(r"\x1b\[[0-9;]*m", "", s))


def row(text: str = "", w: int | None = None) -> str:
    w = w or width()
    pad = w - 4 - visible_len(text)
    return f"{c(CYAN, BOX['v'])} {text}{' ' * max(pad, 0)} {c(CYAN, BOX['v'])}"


def rule(left: str, right: str, title: str = "", right_title: str = "") -> str:
    w = width()
    t = f"{BOX['h']} {title} " if title else ""
    rt = f" {right_title} {BOX['h']}" if right_title else ""
    fill = w - 2 - visible_len(t) - visible_len(rt)
    return c(CYAN, left + t) + c(CYAN, BOX['h'] * max(fill, 0) + rt + right)


def clear() -> None:
    if COLOR:
        sys.stdout.write("\x1b[2J\x1b[H")
    else:
        print("\n" * 2)


# ------------------------------------------------------------------- logging
_log_path: Path | None = None


def log(line: str) -> None:
    global _log_path
    if _log_path is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _log_path = LOG_DIR / f"{SESSION}.log"
    with open(_log_path, "a", encoding="utf-8") as fh:
        fh.write(time.strftime("%H:%M:%S ") + line + "\n")


TAGS = {"OK": (GREEN, " OK "), "HEAL": (GOLD, "HEAL"), "WARN": (GOLD, "WARN"),
        "FAIL": (RED, "FAIL"), "INFO": (GRAY, "INFO"), "RUN": (CYAN, "RUN ")}


def say(level: str, text: str) -> None:
    color, tag = TAGS[level]
    print(f"  {c(color, '[' + tag + ']')} {text}")
    log(f"[{tag}] {text}")


def heading(text: str) -> None:
    print(f"\n  {c(BOLD, text)}")
    log(f"== {text}")


def ask_yes(question: str) -> bool:
    if AUTO or not sys.stdin.isatty():
        return False
    answer = input(f"  {question} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


# ------------------------------------------------------------- self-healing
def ensure_dirs() -> None:
    for d in DATA_DIRS:
        p = ROOT / d
        if not p.exists():
            p.mkdir(parents=True)
            say("HEAL", f"created {d}/")


def ensure_env_file() -> None:
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists() and example.exists():
        shutil.copyfile(example, env)
        say("WARN", ".env created from .env.example - fill in its values (preflight lists what is empty)")


def deps_state() -> tuple[bool, str]:
    missing = [n for n in PROBE_IMPORTS if importlib.util.find_spec(n) is None]
    if missing:
        return False, "missing: " + ", ".join(missing)
    req, stamp = ROOT / REQUIREMENTS, ROOT / ".venv" / ".installed-requirements"
    if req.exists() and (not stamp.exists() or stamp.read_bytes() != req.read_bytes()):
        return False, f"{REQUIREMENTS} changed since the last install" if stamp.exists() else "not installed yet"
    return True, "up to date" if req.exists() else f"no {REQUIREMENTS}"


def install(force: bool = False) -> int:
    req = ROOT / REQUIREMENTS
    if not req.exists():
        say("INFO", f"no {REQUIREMENTS} - nothing to install")
        return 0
    base = [PY, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(req)]
    if force:
        base.insert(5, "--force-reinstall")
    say("HEAL", f"installing from {REQUIREMENTS}{' (force)' if force else ''}")
    rc = run_cmd(base, quiet=True)
    if rc != 0:
        say("HEAL", "retrying without the pip cache")
        rc = run_cmd(base + ["--no-cache-dir"], quiet=True)
    if rc != 0:
        say("FAIL", f"install failed - details in {_log_path}")
        return rc
    shutil.copyfile(req, ROOT / ".venv" / ".installed-requirements")
    say("OK", "dependencies installed")
    return 0


def heal() -> bool:
    heading("Getting ready")
    if sys.version_info < PY_MIN:
        say("FAIL", f"Python {'.'.join(map(str, sys.version_info[:3]))} is older than {'.'.join(map(str, PY_MIN))} - "
                    "install a newer Python, then run with --rebuild")
        return False
    say("OK", f"Python {sys.version.split()[0]} in .venv ({Path(PY).parent.parent.name})")
    ok, why = deps_state()
    if not ok:
        say("HEAL", f"dependencies: {why}")
        if install() != 0:
            return False
    else:
        say("OK", f"dependencies {why}")
    ensure_dirs()
    ensure_env_file()
    return True


def preflight(verbose: bool = True) -> int:
    if not (ROOT / PREFLIGHT).exists():
        say("WARN", f"{PREFLIGHT} not found - checks skipped")
        return 0
    cmd = [PY, str(ROOT / PREFLIGHT), "--min-python", ".".join(map(str, PY_MIN)), "--dirs", " ".join(DATA_DIRS)]
    if PROBE_IMPORTS:
        cmd += ["--imports", " ".join(PROBE_IMPORTS)]
    if APP_KIND == "server":
        cmd += ["--port", str(PORT)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in (proc.stdout + proc.stderr).splitlines():
        log(line)
        if verbose:
            print("  " + line.strip() if "FAIL" not in line else "  " + c(RED, line.strip()))
    if proc.returncode == 0:
        say("OK", "preflight passed")
    elif proc.returncode == 2:
        say("WARN", "preflight passed with warnings - review them above")
        return 0
    else:
        say("FAIL", "preflight found problems - fix the items above, then run again")
    return proc.returncode


# ------------------------------------------------------------------ running
def run_cmd(cmd: list[str], env: dict | None = None, quiet: bool = False) -> int:
    log("$ " + " ".join(cmd))
    sys.stdout.flush()
    full_env = {**os.environ, **(env or {})}
    try:
        if quiet:
            proc = subprocess.run(cmd, env=full_env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            for line in (proc.stdout + proc.stderr).splitlines():
                log("  " + line)
            return proc.returncode
        proc = subprocess.Popen(cmd, env=full_env)
        try:
            return proc.wait()
        except KeyboardInterrupt:
            # Child process isi console ko share karta hai, toh Ctrl+C use bhi mila; use aaram se
            # band hone ka time do, phir rok do.
            say("INFO", "stopping (Ctrl+C)")
            try:
                return proc.wait(timeout=10)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                proc.terminate()
                try:
                    return proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    return proc.wait()
    except FileNotFoundError as exc:
        say("FAIL", f"cannot start {cmd[0]}: {exc}")
        return 127


def new_run_id() -> str:
    rid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    os.environ["APP_RUN_ID"] = rid
    os.environ["APP_TRACE"] = os.environ.get("APP_TRACE", "1")
    log(f"run id {rid}")
    return rid


def act_run(extra: list[str]) -> int:
    if preflight() != 0:
        return 1
    new_run_id()
    if APP_KIND != "server":
        heading(f"Running {APP_MODULE}")
        return run_cmd([PY, "-m", APP_MODULE, *extra])
    while True:
        heading(f"Serving {APP_NAME} at {APP_URL}  (Ctrl+C to stop)")
        if OPEN_BROWSER and not AUTO:
            threading.Timer(2.5, lambda: webbrowser.open(APP_URL)).start()
        rc = run_cmd([PY, *SERVER_ARGS, *extra])
        if rc == 0:
            return 0
        say("FAIL", f"server stopped with exit {rc} - is port {PORT} busy? try: ports")
        if not ask_yes("Restart the server?"):
            return rc


def act_trace(extra: list[str]) -> int:
    if preflight() != 0:
        return 1
    if not (ROOT / TRACE_KIT).exists():
        say("FAIL", f"{TRACE_KIT} not found - copy trace_kit.py into the package (skill observability-tracing)")
        return 2
    new_run_id()
    heading("Tracing every project line (slower)")
    target = SERVER_ARGS if APP_KIND == "server" else ["-m", APP_MODULE]
    return run_cmd([PY, str(ROOT / TRACE_KIT), "run", *target, *extra], env={"APP_TRACE_LINES": "1"})


def act_test(extra: list[str]) -> int:
    if preflight() != 0:
        return 1
    new_run_id()
    if importlib.util.find_spec("pytest") is None:
        heading("Tests (unittest - pytest is not installed)")
        return run_cmd([PY, "-m", "unittest", "discover", "-q"])
    if "--all" in extra:
        heading("Tests: offline + live (network and keys needed)")
        cmd = [PY, "-m", "pytest", "-q"]
    elif "--live" in extra:
        heading("Tests: live only")
        cmd = [PY, "-m", "pytest", "-q", "-m", TEST_LIVE_MARKER]
    else:
        heading("Tests: offline only (live tests: test --all)")
        cmd = [PY, "-m", "pytest", "-q", "-m", f"not {TEST_LIVE_MARKER}"]
    rc = run_cmd(cmd + [a for a in extra if a not in ("--all", "--live")])
    if rc == 5:
        say("WARN", "no tests were collected - that is not a pass")
    return rc


def act_diagnose(_: list[str]) -> int:
    heading("Diagnose")
    ok, why = deps_state()
    say("OK" if ok else "WARN", f"dependencies {why}")
    return preflight()


def act_report(_: list[str]) -> int:
    if not (ROOT / TRACE_KIT).exists():
        say("FAIL", f"{TRACE_KIT} not found")
        return 2
    heading("Latest trace")
    return run_cmd([PY, str(ROOT / TRACE_KIT), "report"])


def act_repair(_: list[str]) -> int:
    heading("Repair")
    rc = install(force=True)
    if rc != 0:
        say("INFO", "if pip itself is broken, run:  run.bat --rebuild   (or ./run.sh --rebuild)")
    return rc


def _port_owners(port: int) -> list[tuple[str, str]]:
    owners: list[tuple[str, str]] = []
    if IS_WIN:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, errors="replace").stdout
        pids = {ln.split()[-1] for ln in out.splitlines()
                if "LISTENING" in ln and ln.split()[1].endswith(f":{port}")} if out else set()
        for pid in sorted(pids):
            info = subprocess.run(["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                                  capture_output=True, text=True, errors="replace").stdout.strip()
            owners.append((pid, info.split(",")[0].strip('"') if info.startswith('"') else "?"))
    elif shutil.which("lsof"):
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True).stdout
        for pid in sorted(set(out.split())):
            name = subprocess.run(["ps", "-p", pid, "-o", "comm="], capture_output=True, text=True).stdout.strip()
            owners.append((pid, name or "?"))
    return owners


def act_ports(_: list[str]) -> int:
    heading(f"Port {PORT}")
    if not IS_WIN and not shutil.which("lsof"):
        say("WARN", "lsof is not installed - cannot list port owners (macOS has it; Linux: install lsof)")
        return 2
    owners = _port_owners(PORT)
    if not owners:
        say("OK", f"port {PORT} is free")
        return 0
    for pid, name in owners:
        say("WARN", f"port {PORT} is used by {name} (PID {pid})")
    for pid, name in owners:
        if ask_yes(f"Stop {name} (PID {pid})? This ends that program."):
            if IS_WIN:
                rc = subprocess.run(["taskkill", "/pid", pid, "/f"], capture_output=True).returncode
            else:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    rc = 0
                except OSError:
                    rc = 1
            say("OK" if rc == 0 else "FAIL", f"{'stopped' if rc == 0 else 'could not stop'} PID {pid}")
    return 1 if _port_owners(PORT) else 0


def act_logs(_: list[str]) -> int:
    heading("Recent launcher logs")
    logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime)[-5:]
    if not logs:
        say("INFO", "no logs yet")
        return 0
    for p in logs:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        status = next((l for l in reversed(lines) if "exit" in l), "")
        print(f"  {c(GRAY, p.name)}  {status[9:] if status else ''}")
    latest = logs[-1].read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
    print(f"\n  {c(BOLD, 'tail of ' + logs[-1].name)}")
    for l in latest:
        print("   " + l)
    return 0


ACTIONS: list[tuple[str, str, str, object]] = [
    ("run", "Run", "start the app with step tracing" if APP_KIND != "server" else f"serve at {APP_URL}", act_run),
    ("trace", "Trace", "run with line-level tracing, report after", act_trace),
    ("test", "Test", "offline test suite", act_test),
    ("testall", "Test all", "offline + live tests (network, keys)", lambda a: act_test(["--all", *a])),
    ("diagnose", "Diagnose", "preflight: python, packages, port, folders, .env", act_diagnose),
    ("report", "Report", "summarise the latest trace", act_report),
    ("repair", "Repair", "reinstall dependencies", act_repair),
    ("ports", "Ports", f"who is using port {PORT}", act_ports),
    ("logs", "Logs", "recent launcher runs and the latest log", act_logs),
]
for _name, _label, _desc, _argv in EXTRA_ACTIONS:
    ACTIONS.append((_name, _label, _desc, lambda a, argv=_argv: (new_run_id(), run_cmd([PY, *argv, *a]))[1]))


def perform(name: str, extra: list[str]) -> int:
    for key, label, _, fn in ACTIONS:
        if key == name:
            start = time.time()
            log(f"action {key} {' '.join(extra)}")
            try:
                rc = fn(extra)  # type: ignore[operator]
            except KeyboardInterrupt:
                rc = 130
            secs = time.time() - start
            log(f"exit {rc} after {secs:.1f}s")
            footer(label, rc, secs)
            return rc
    say("FAIL", f"unknown action '{name}' - one of: {', '.join(a[0] for a in ACTIONS)}")
    return 2


def footer(label: str, rc: int, secs: float) -> None:
    rid = os.environ.get("APP_RUN_ID", "")
    print()
    state = c(GREEN, "done") if rc == 0 else c(RED, "stopped")
    print(f"  {state} {label} {BOX['dot']} exit {rc} {BOX['dot']} {secs:.1f}s")
    print(c(GRAY, f"  log    {_log_path.relative_to(ROOT) if _log_path else '-'}"))
    trace = ROOT / "logs" / "trace" / f"{rid}.jsonl"
    if rid and trace.exists():
        print(c(GRAY, f"  trace  {trace.relative_to(ROOT)}   (Report shows it)"))


# --------------------------------------------------------------------- menu
def read_key() -> str:
    scripted = os.environ.get("LAUNCHER_KEYS")
    if scripted is not None:
        keys = [k for k in scripted.split(",") if k]
        if not keys:
            return "q"
        os.environ["LAUNCHER_KEYS"] = ",".join(keys[1:])
        return keys[0]
    if IS_WIN:
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
        return {"\r": "enter", "\x1b": "q", "\x03": "q"}.get(ch, ch)
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return {"[A": "up", "[B": "down"}.get(seq, "q")
        return {"\r": "enter", "\n": "enter", "\x03": "q"}.get(ch, ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def draw(selected: int, status: str, last: str) -> None:
    clear()
    w = width()
    print(rule(BOX["tl"], BOX["tr"], c(BOLD, APP_NAME), f"session {SESSION}"))
    print(row(c(GRAY, status), w))
    print(row(c(GRAY, last) if last else "", w))
    print(c(CYAN, BOX["ml"] + BOX["h"] * (w - 2) + BOX["mr"]))
    for i, (_, label, desc, _) in enumerate(ACTIONS):
        num = str(i + 1) if i < 9 else " "
        if i == selected:
            line = c(GOLD, f"{BOX['arrow']} {num}  ") + c(BOLD, f"{label:<10}") + "  " + desc
        else:
            line = f"  {c(GRAY, num)}  {label:<10}  " + c(GRAY, desc)
        print(row(line, w))
    print(row("", w))
    hint = f"Up/Down move {BOX['dot']} Enter run {BOX['dot']} 1-9 jump {BOX['dot']} q quit"
    print(rule(BOX["bl"], BOX["br"], c(GRAY, hint)))


def menu() -> int:
    selected, last, rc = 0, "", 0
    ok, why = deps_state()
    status = (f"python {sys.version.split()[0]} {BOX['dot']} .venv ok {BOX['dot']} "
              f"deps {'ok' if ok else why} {BOX['dot']} {APP_KIND} {APP_MODULE if APP_KIND != 'server' else APP_URL}")
    interactive_keys = sys.stdin.isatty() or os.environ.get("LAUNCHER_KEYS") is not None
    while True:
        if not interactive_keys:
            for i, (_, label, desc, _) in enumerate(ACTIONS):
                print(f"  {i + 1}. {label:<10} {desc}")
            choice = input("  choose a number (q to quit): ").strip().lower()
            if choice in ("", "q"):
                return 0  # quit karna user ki marzi hai; har action apna exit pehle hi dikha chuka hai
            key = choice
        else:
            draw(selected, status, last)
            key = read_key()
        if key in ("q", "Q"):
            clear()
            return 0
        if key in ("up", "k"):
            selected = (selected - 1) % len(ACTIONS)
            continue
        if key in ("down", "j"):
            selected = (selected + 1) % len(ACTIONS)
            continue
        if key.isdigit() and 1 <= int(key) <= min(9, len(ACTIONS)):
            selected = int(key) - 1
            key = "enter"
        if key != "enter":
            continue
        clear()
        name, label = ACTIONS[selected][0], ACTIONS[selected][1]
        rc = perform(name, [])
        last = f"last: {label} {BOX['dot']} exit {rc} {BOX['dot']} run {os.environ.get('APP_RUN_ID', '-')}"
        if interactive_keys and os.environ.get("LAUNCHER_KEYS") is None:
            print(c(GRAY, "\n  press any key for the menu"))
            read_key()


def main() -> int:
    log(f"session {SESSION} {APP_NAME} args={ARGS}")
    if not heal():
        return 1
    if ARGS:
        return perform(ARGS[0], ARGS[1:])
    return menu()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
