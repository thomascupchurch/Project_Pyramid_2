# Justfile task recipes (alternative to Makefile)

set shell := ['bash', '-cu']

PY ?= python3
VENV ?= .venv
VENV_PY := {{VENV}}/bin/python

@default: help

help:
  @echo "Available recipes:" && \
  echo "  setup     - create venv & install" && \
  echo "  run       - start app" && \
  echo "  verify    - run verify_env" && \
  echo "  freeze    - pip freeze snapshot" && \
  echo "  clean     - remove venv" && \
  echo "  health    - curl /health"

setup:
  {{PY}} -m venv {{VENV}}
  {{VENV_PY}} -m pip install --upgrade pip setuptools wheel
  {{VENV_PY}} -m pip install -r requirements.txt

run:
  SIGN_APP_HOST=127.0.0.1 SIGN_APP_PORT=8050 {{VENV_PY}} app.py

verify:
  {{VENV_PY}} scripts/verify_env.py --json

freeze:
  {{VENV_PY}} -m pip freeze > .venv_freeze_`date +%Y%m%d_%H%M%S`.txt

clean:
  rm -rf {{VENV}}

health:
  curl -fsS http://127.0.0.1:8050/health | jq . || echo "Health endpoint not reachable."