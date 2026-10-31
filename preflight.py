"""preflight - check that this machine can run the project, and say exactly how to fix it (P8).

Standard library only, Python 3.9+. The launcher calls it before every run mode; you can too:

    python preflight.py --min-python 3.10 --imports "fastapi uvicorn" --port 8000 \
                        --dirs "data logs" --env-example .env.example

Exit 0 when everything passes, 1 when something needs fixing (each failure prints a FIX line).
Never prints the value of an environment variable - only its name.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import socket
import sys
from pathlib import Path


def check_python(minimum: str) -> list[str]:
    want = tuple(int(p) for p in minimum.split("."))
    have = sys.version_info[: len(want)]
    if have < want:
        return [f"Python {sys.version.split()[0]} is older than {minimum}. "
                f"FIX: install Python {minimum}+ and re-run the launcher (it rebuilds .venv)."]
    return []


def check_imports(names: list[str]) -> list[str]:
    missing = [n for n in names if importlib.util.find_spec(n) is None]
    if missing:
        return [f"missing packages: {', '.join(missing)}. "
                f"FIX: the launcher reinstalls from the lockfile; or run: python -m pip install -r requirements.txt"]
    return []


def check_port(port: int) -> list[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return [f"port {port} is already in use. FIX: stop the other process "
                    f"(Windows: netstat -ano | findstr :{port}; macOS/Linux: lsof -i :{port}) or set another PORT."]
    return []


def check_dirs(dirs: list[str]) -> list[str]:
    problems = []
    for d in dirs:
        path = Path(d)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            print(f"  made   {d}/")
        elif not path.is_dir():
            problems.append(f"{d} exists but is not a folder. FIX: rename or remove it.")
    return problems


def _values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            values[key] = value.strip().strip('"').strip("'")
    return values


def check_env(example: str) -> list[str]:
    """Example ki har key ki .env ya environment mein khaali-nahi value honi chahiye.
    Sirf key ke naam print hote hain - value kabhi nahi."""
    ex = Path(example)
    if not ex.exists():
        return []
    env = ex.with_name(".env")
    needed = list(_values(ex))
    have = _values(env) if env.exists() else {}
    missing = [k for k in needed if not (have.get(k) or os.environ.get(k))]
    if not missing:
        return []
    if not env.exists():
        return [f".env is missing. FIX: copy {example} to .env and fill in: {', '.join(missing)}"]
    return [f".env has no value for: {', '.join(missing)}. FIX: fill them in .env (see {example}); "
            f"the app will not run on blank settings."]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-python", default="3.10")
    ap.add_argument("--imports", default="", help="space-separated import names to probe")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--dirs", default="", help="space-separated folders that must exist")
    ap.add_argument("--env-example", default=".env.example")
    a = ap.parse_args(argv)

    problems: list[str] = []
    problems += check_python(a.min_python)
    problems += check_imports(a.imports.split())
    if a.port:
        problems += check_port(a.port)
    problems += check_dirs(a.dirs.split())
    problems += check_env(a.env_example)

    if problems:
        for p in problems:
            print(f"  FAIL   {p}")
        print(f"preflight: {len(problems)} problem(s)")
        return 1
    print("preflight: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
