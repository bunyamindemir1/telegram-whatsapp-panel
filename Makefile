PYTHON ?= python3.9

.PHONY: setup quick install start stop smoke preflight dev test e2e locales screenshot publish-check docker-up docker-down docker-logs clean

setup:
	@chmod +x setup.sh install.sh start.sh stop.sh scripts/smoke_local.sh && ./setup.sh

quick: install start

install:
	@chmod +x install.sh && ./install.sh

start:
	@chmod +x start.sh && ./start.sh

stop:
	@chmod +x stop.sh && ./stop.sh

smoke:
	@chmod +x scripts/smoke_local.sh && ./scripts/smoke_local.sh

dev:
	@test -d .venv || $(PYTHON) -m venv .venv
	@. .venv/bin/activate && pip install -q -r requirements.txt
	@cd whatsapp-bridge && npm install --silent
	@. .venv/bin/activate && $(PYTHON) run.py

test:
	@$(PYTHON) -m pytest -q

e2e:
	@$(PYTHON) -m pytest tests/e2e -q -m e2e

locales:
	@$(PYTHON) scripts/validate_locales.py

screenshot:
	@$(PYTHON) scripts/capture_screenshot.py

preflight:
	@chmod +x scripts/preflight_public.sh && ./scripts/preflight_public.sh

publish-check: locales test
	@node --check whatsapp-bridge/server.js
	@./scripts/prepare_github.sh

docker-up:
	@docker compose up -d --build

docker-down:
	@docker compose down

docker-logs:
	@docker compose logs -f panel

clean:
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache
