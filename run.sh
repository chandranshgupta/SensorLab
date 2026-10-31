#!/usr/bin/env bash
# run.sh - macOS aur Linux par is project ko chalane ka ek hi tareeka (prime directive P8).
#   ./run.sh              arrow-key menu      ./run.sh run | trace | test | diagnose | report | repair | ports | logs
#   ./run.sh --rebuild    pehle .venv mitao aur dobara banao
#   flags --plain (bina colour)  --yes (kabhi kuch mat poochho)
# Yeh file sirf Python dhoondhti hai aur .venv banati hai; baaki sab launcher.py karta hai.
set -u
cd "$(dirname "$0")" || exit 2
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
PY_MIN="3.10"
VPY=.venv/bin/python

ok_version() { "$@" -c "import sys; sys.exit(0 if sys.version_info >= tuple(map(int, '$PY_MIN'.split('.'))) else 1)" >/dev/null 2>&1; }

case " $* " in *" --rebuild "*) [ -d .venv ] && { printf '  [HEAL] --rebuild: removing .venv\n'; rm -rf .venv; } ;; esac

if [ -x "$VPY" ] && ! ok_version "$VPY"; then
  printf '  [HEAL] .venv is stale or from another machine - rebuilding it\n'
  rm -rf .venv
fi

if [ ! -x "$VPY" ]; then
  PY=""
  for cand in python3 python python3.13 python3.12 python3.11 python3.10; do
    command -v "$cand" >/dev/null 2>&1 && ok_version "$cand" && { PY=$cand; break; }
  done
  if [ -z "$PY" ]; then
    printf '\n  [FAIL] Python %s+ was not found.\n  How to fix:\n' "$PY_MIN"
    printf '    macOS:          brew install python   (or the installer from python.org)\n'
    printf '    Debian/Ubuntu:  sudo apt install python3 python3-venv\n'
    printf '    Fedora:         sudo dnf install python3\n'
    printf '  Then run ./run.sh again.\n\n'
    exit 1
  fi
  printf '  [HEAL] creating .venv with %s\n' "$PY"
  "$PY" -m venv .venv || { printf '  [FAIL] could not create .venv (Debian/Ubuntu: sudo apt install python3-venv)\n'; exit 1; }
fi

exec "$VPY" launcher.py "$@"
