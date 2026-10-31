"""trace_kit - connected step tracing and optional line tracing for Python projects (P9).

Standard library only. Copy this file into your package (for example app/trace_kit.py).

    from app.trace_kit import traced, touch, new_trace

    @traced                         # every core function: one span per call
    def load_orders(path):
        touch("file", path, "read")  # record what the step touched
        ...

    with new_trace("cli: report"):  # at each entry point (request, command, job, UI action)
        load_orders("data/orders.csv")

Run modes (the launcher sets these):
    APP_TRACE=1              write spans to logs/trace/<run_id>.jsonl (default on; 0 disables)
    APP_TRACE_LINES=1        also record every project line executed (slower; trace mode only)
    APP_TRACE_VALUES=1       include short, redacted argument values (default: types and sizes)
    APP_TRACE_DIR=path       where trace files go (default logs/trace)
    APP_TRACE_ECHO=1         also print each span to stderr

Command line:
    python trace_kit.py run -m app.main [args]   run a module with line tracing, then report
    python trace_kit.py run path/script.py       same for a script
    python trace_kit.py report [trace.jsonl]     summarise a trace (latest run by default)

Secrets: any argument, keyword or metadata name matching password, secret, token, key,
authorization, cookie or credential is recorded as "***". Values are never recorded unless
APP_TRACE_VALUES=1, and then truncated and redacted.
"""
from __future__ import annotations

import atexit
import contextlib
import contextvars
import functools
import inspect
import itertools
import json
import os
import re
import runpy
import sys
import threading
import time
import traceback
import uuid
from collections import defaultdict
from pathlib import Path

_ENABLED = os.environ.get("APP_TRACE", "1") != "0"
_VALUES = os.environ.get("APP_TRACE_VALUES") == "1"
_ECHO = os.environ.get("APP_TRACE_ECHO") == "1"
_DIR = Path(os.environ.get("APP_TRACE_DIR", "logs/trace"))
_ROOT = Path(os.environ.get("APP_TRACE_ROOT", os.getcwd())).resolve()
RUN_ID = os.environ.get("APP_RUN_ID") or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
TRACE_FILE = _DIR / f"{RUN_ID}.jsonl"

_SECRET = re.compile(r"pass(word)?|secret|token|api[_-]?key|authorization|cookie|credential", re.I)
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_span: contextvars.ContextVar[tuple[str, int] | None] = contextvars.ContextVar("span", default=None)
_steps = itertools.count(1)
_lock = threading.Lock()
_fh = None


def _rel(path: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(_ROOT)).replace("\\", "/")
    except (ValueError, OSError):
        return path.replace("\\", "/")


def _emit(event: dict) -> None:
    global _fh
    if not _ENABLED:
        return
    event.setdefault("ts", round(time.time(), 6))
    event.setdefault("run_id", RUN_ID)
    line = json.dumps(event, default=str, ensure_ascii=False)
    with _lock:
        if _fh is None:
            _DIR.mkdir(parents=True, exist_ok=True)
            _fh = open(TRACE_FILE, "a", encoding="utf-8")
        _fh.write(line + "\n")
        _fh.flush()
    if _ECHO:
        print(f"[trace] {line}", file=sys.stderr)


def _summary(name: str, value) -> object:
    if _SECRET.search(name or ""):
        return "***"
    kind = type(value).__name__
    size = len(value) if hasattr(value, "__len__") and not isinstance(value, type) else None
    if not _VALUES:
        return {"type": kind, "size": size} if size is not None else {"type": kind}
    text = repr(value)
    text = re.sub(r"(?i)(pass(word)?|secret|token|api[_-]?key)(['\"]?\s*[:=]\s*)\S+", r"\1\3***", text)
    return text[:80] + ("..." if len(text) > 80 else "")


@contextlib.contextmanager
def new_trace(name: str = "entry", origin: str | None = None):
    """Entry point pe naya trace shuru karo. Andar ke calls chal rahe trace ko hi use karte hain."""
    if _trace_id.get() is not None:
        yield _trace_id.get()
        return
    tid = uuid.uuid4().hex[:16]
    token = _trace_id.set(tid)
    if origin is None:
        caller = sys._getframe(2) if hasattr(sys, "_getframe") else None
        origin = f"{_rel(caller.f_code.co_filename)}:{caller.f_lineno}" if caller else "?"
    file, _, line = origin.rpartition(":")
    _emit({"kind": "trace_start", "trace_id": tid, "name": name, "file": file or origin,
           "line": int(line) if line.isdigit() else None})
    start = time.perf_counter()
    status = "ok"
    try:
        yield tid
    except BaseException as exc:
        status = f"error: {type(exc).__name__}"
        raise
    finally:
        _emit({"kind": "trace_end", "trace_id": tid, "name": name, "status": status,
               "ms": round((time.perf_counter() - start) * 1000, 3)})
        _trace_id.reset(token)


def touch(kind: str, target: str, op: str = "read", **meta) -> None:
    """Step ne jo resource chhua use record karo: kind file|table|http|queue|cache|env, op read|write|call."""
    span = _span.get()
    _emit({"kind": "touch", "trace_id": _trace_id.get(), "span": span[0] if span else None,
           "resource": kind, "target": "***" if _SECRET.search(str(target)) else str(target), "op": op,
           "meta": {k: ("***" if _SECRET.search(k) else v) for k, v in meta.items()}})


def traced(fn=None, *, name: str | None = None):
    """Decorator: har call ka ek span - file, function, line, step, inputs ka summary, duration, status."""
    if fn is None:
        return lambda f: traced(f, name=name)
    code = fn.__code__
    label = name or fn.__qualname__
    where = {"file": _rel(code.co_filename), "function": label, "line": code.co_firstlineno}
    try:
        params = list(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        params = []

    def _start(args, kwargs):
        implicit = None
        caller = sys._getframe(2)
        if _trace_id.get() is None:
            implicit = new_trace(f"implicit: {label}",
                                 origin=f"{_rel(caller.f_code.co_filename)}:{caller.f_lineno}")
            implicit.__enter__()
        parent = _span.get()
        span_id = uuid.uuid4().hex[:8]
        depth = parent[1] + 1 if parent else 0
        inputs = {p: _summary(p, a) for p, a in zip(params, args)}
        inputs.update({k: _summary(k, v) for k, v in kwargs.items()})
        _emit({"kind": "span_start", "trace_id": _trace_id.get(), "span": span_id,
               "parent": parent[0] if parent else None, "depth": depth, "step": next(_steps),
               **where, "called_from": f"{_rel(caller.f_code.co_filename)}:{caller.f_lineno}",
               "inputs": inputs})
        return implicit, _span.set((span_id, depth)), span_id, time.perf_counter()

    def _end(state, result=None, exc=None):
        implicit, token, span_id, start = state
        event = {"kind": "span_end", "trace_id": _trace_id.get(), "span": span_id, **where,
                 "ms": round((time.perf_counter() - start) * 1000, 3)}
        if exc is None:
            event["status"] = "ok"
            event["output"] = _summary("result", result)
        else:
            tb = traceback.extract_tb(exc.__traceback__)
            event["status"] = "error"
            event["error"] = {"type": type(exc).__name__, "message": str(exc)[:200],
                              "at": [f"{_rel(f.filename)}:{f.lineno}" for f in tb
                                     if Path(f.filename).name != "trace_kit.py"][-5:]}
        _emit(event)
        _span.reset(token)
        if implicit is not None:
            implicit.__exit__(type(exc) if exc else None, exc, exc.__traceback__ if exc else None)

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            state = _start(args, kwargs)
            try:
                result = await fn(*args, **kwargs)
            except BaseException as exc:
                _end(state, exc=exc)
                raise
            _end(state, result=result)
            return result
        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        state = _start(args, kwargs)
        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:
            _end(state, exc=exc)
            raise
        _end(state, result=result)
        return result
    return wrapper


# --------------------------------------------------------------- line tracing
_lines: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
_line_tracing = False
_tool = None


def _in_project(filename: str) -> bool:
    if not filename or filename.startswith("<"):
        return False
    try:
        path = Path(filename).resolve()
        path.relative_to(_ROOT)
    except (ValueError, OSError):
        return False
    parts = set(path.parts)
    return not ({".venv", "venv", "site-packages", "node_modules"} & parts) and path.name != "trace_kit.py"


def enable_line_tracing() -> None:
    """Project ki har chali hui line record karo. sys.monitoring (3.12+) ya sys.settrace use hota hai."""
    global _line_tracing, _tool
    if _line_tracing or not _ENABLED:
        return
    _line_tracing = True
    if hasattr(sys, "monitoring"):
        mon = sys.monitoring
        tool = next((t for t in (mon.COVERAGE_ID, mon.PROFILER_ID, mon.OPTIMIZER_ID) if mon.get_tool(t) is None), None)
        if tool is not None:
            _tool = tool
            mon.use_tool_id(tool, "trace_kit")

            def on_line(code, line):
                if line <= 0 or not _in_project(code.co_filename):
                    return mon.DISABLE
                _lines[code.co_filename][line] += 1
                return None
            mon.register_callback(tool, mon.events.LINE, on_line)
            mon.set_events(tool, mon.events.LINE)
            atexit.register(_write_lines)
            return

    cache: dict[str, bool] = {}

    def local(frame, event, arg):
        if event == "line" and frame.f_lineno > 0:
            _lines[frame.f_code.co_filename][frame.f_lineno] += 1
        return local

    def glob(frame, event, arg):
        f = frame.f_code.co_filename
        if f not in cache:
            cache[f] = _in_project(f)
        return local if cache[f] else None
    sys.settrace(glob)
    threading.settrace(glob)
    atexit.register(_write_lines)


def disable_line_tracing() -> None:
    global _line_tracing
    if not _line_tracing:
        return
    if _tool is not None:
        sys.monitoring.set_events(_tool, 0)
        sys.monitoring.free_tool_id(_tool)
    else:
        sys.settrace(None)
        threading.settrace(None)
    _line_tracing = False


def _write_lines() -> None:
    files = {_rel(f): {"lines": sorted(c), "hits": sum(c.values())} for f, c in _lines.items()}
    _emit({"kind": "lines", "files": files})


if os.environ.get("APP_TRACE_LINES") == "1":
    enable_line_tracing()


# --------------------------------------------------------------------- report
def _ranges(lines: list[int]) -> str:
    out, start, prev = [], None, None
    for n in lines:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = n
    if start is not None:
        out.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(out)


def report(path: str | None = None, out=sys.stdout) -> int:
    if path is None:
        files = sorted(_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not files:
            print(f"trace_kit: no traces in {_DIR}", file=out)
            return 1
        path = str(files[-1])
    events = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    starts = {e["span"]: e for e in events if e["kind"] == "span_start"}
    ends = {e["span"]: e for e in events if e["kind"] == "span_end"}
    traces = [e for e in events if e["kind"] == "trace_start"]
    touches = [e for e in events if e["kind"] == "touch"]
    lines = [e for e in events if e["kind"] == "lines"]
    errors = [e for e in ends.values() if e.get("status") == "error"]

    print(f"trace report - {path}", file=out)
    print(f"  traces {len(traces)} | steps {len(starts)} | errors {len(errors)} | resources touched {len(touches)}", file=out)
    for t in traces:
        print(f"\n  trace {t['trace_id']}  {t['name']}  (from {t.get('file')}:{t.get('line')})", file=out)
        for s in sorted((s for s in starts.values() if s["trace_id"] == t["trace_id"]), key=lambda s: s["step"]):
            e = ends.get(s["span"], {})
            mark = "ok " if e.get("status") == "ok" else "ERR" if e else "..."
            print(f"    {mark} #{s['step']:<4}{'  ' * s['depth']}{s['function']}  {s['file']}:{s['line']}"
                  f"  called from {s['called_from']}  {e.get('ms', '?')} ms", file=out)
            if e.get("status") == "error":
                err = e["error"]
                print(f"         {'  ' * s['depth']}{err['type']}: {err['message']}  at {' > '.join(err['at'])}", file=out)
            for r in (r for r in touches if r.get("span") == s["span"]):
                print(f"         {'  ' * s['depth']}touched {r['resource']} {r['op']} {r['target']}", file=out)
    slow = sorted(ends.values(), key=lambda e: e.get("ms", 0), reverse=True)[:5]
    if slow:
        print("\n  slowest steps:", file=out)
        for e in slow:
            print(f"    {e['ms']:>10} ms  {e['function']}  {e['file']}:{e['line']}", file=out)
    for l in lines:
        print(f"\n  lines executed ({len(l['files'])} project files):", file=out)
        for f, info in sorted(l["files"].items()):
            print(f"    {f}: {len(info['lines'])} lines, {info['hits']} hits  [{_ranges(info['lines'])}]", file=out)
    return 1 if errors else 0


def _main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "report":
        return report(argv[1] if len(argv) > 1 else None)
    if argv[0] == "run" and len(argv) > 1:
        # Program is module ko doosre naam se import kar sakta hai (jaise app.trace_kit); run id share
        # karo taaki har copy ek hi trace file mein likhe, aur plain naam ka alias bhi bana do.
        os.environ["APP_RUN_ID"] = RUN_ID
        sys.modules.setdefault("trace_kit", sys.modules[__name__])
        enable_line_tracing()
        code = 0
        try:
            with new_trace("run " + " ".join(argv[1:3])):
                if argv[1] == "-m":
                    # "python -m" jaisa behave karo: working directory import ho sake, na ki
                    # woh folder jismein yeh file padi hai.
                    if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
                        sys.path[0] = os.getcwd()
                    else:
                        sys.path.insert(0, os.getcwd())
                    sys.argv = argv[2:]
                    runpy.run_module(argv[2], run_name="__main__", alter_sys=True)
                else:
                    sys.argv = argv[1:]
                    runpy.run_path(argv[1], run_name="__main__")
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        except BaseException:
            traceback.print_exc()
            code = 1
        disable_line_tracing()
        sys.stdout.flush()
        _write_lines()
        atexit.unregister(_write_lines)
        print(file=sys.stderr)
        report(str(TRACE_FILE), out=sys.stderr)
        print(f"\nfull trace: {TRACE_FILE}", file=sys.stderr)
        return code
    print("usage: trace_kit.py run -m module [args] | run script.py [args] | report [file]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
