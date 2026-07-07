PYTHON ?= python3.9
ROOT := $(abspath ..)

.PHONY: setup quick install start stop smoke preflight dev test e2e locales screenshot publish-check docker-up docker-down docker-logs clean

setup:
	@chmod +x scripts/setup.sh scripts/install.sh scripts/start.sh scripts/stop.sh scripts/smoke_local.sh && ./scripts/setup.sh

quick: install start

install:
	@chmod +x scripts/install.sh && ./scripts/install.sh

start:
	@chmod +x scripts/start.sh && ./scripts/start.sh

stop:
	@chmod +x scripts/stop.sh && ./scripts/stop.sh

smoke:
	@chmod +x scripts/smoke_local.sh && ./scripts/smoke_local.sh

dev:
	@test -d "$(ROOT)/.venv" || $(PYTHON) -m venv "$(ROOT)/.venv"
	@. "$(ROOT)/.venv/bin/activate" && pip install -q -r config/requirements.txt
	@cd whatsapp-bridge && npm install --silent
	@cd "$(ROOT)" && . .venv/bin/activate && PYTHONPATH=src $(PYTHON) src/scripts/run.py

test:
	@cd "$(ROOT)" && PYTHONPATH=src $(PYTHON) -m pytest -q -c src/config/pytest.ini

e2e:
	@cd "$(ROOT)" && PYTHONPATH=src $(PYTHON) -m pytest src/tests/e2e -q -c src/config/pytest.ini -m e2e

locales:
	@$(PYTHON) scripts/validate_locales.py

screenshot:
	@cd "$(ROOT)" && PYTHONPATH=src $(PYTHON) src/scripts/capture_screenshot.py

preflight:
	@chmod +x scripts/preflight_public.sh && ./scripts/preflight_public.sh

publish-check: locales test
	@node --check whatsapp-bridge/server.js
	@./scripts/prepare_github.sh

docker-up:
	@cd "$(ROOT)" && docker compose up -d --build

docker-down:
	@cd "$(ROOT)" && docker compose down

docker-logs:
	@cd "$(ROOT)" && docker compose logs -f panel

clean:
	@find "$(ROOT)" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@rm -rf "$(ROOT)/.pytest_cache"
