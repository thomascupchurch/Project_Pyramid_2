SHELL := /bin/bash

PYTHON ?= python3
VENV ?= .venv
VENV_PY := $(VENV)/bin/python

.PHONY: help setup run verify clean freeze health

help:
	@echo "Targets:"; \
	echo "  setup   - create venv and install requirements"; \
	echo "  run     - run app.py in venv"; \
	echo "  verify  - run verify_env"; \
	echo "  freeze  - output installed versions"; \
	echo "  clean   - remove venv"; \
	echo "  health  - curl local /health endpoint (requires app running)"

$(VENV_PY):
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install --upgrade pip setuptools wheel

setup: $(VENV_PY)
	$(VENV_PY) -m pip install -r requirements.txt

run: $(VENV_PY)
	SIGN_APP_HOST=127.0.0.1 SIGN_APP_PORT=8050 $(VENV_PY) app.py

verify: $(VENV_PY)
	$(VENV_PY) scripts/verify_env.py --json

freeze: $(VENV_PY)
	$(VENV_PY) -m pip freeze > .venv_freeze_$(shell date +%Y%m%d_%H%M%S).txt

clean:
	rm -rf $(VENV)

health:
	curl -fsS http://127.0.0.1:8050/health | jq . || echo "Health endpoint not reachable."