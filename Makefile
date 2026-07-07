PYTHON ?= python3.9

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
	@test -d .venv || $(PYTHON) -m venv .venv
	@. .venv/bin/activate && pip install -q -r config/requirements.txt
	@cd whatsapp-bridge && npm install --silent
	@. .venv/bin/activate && $(PYTHON) scripts/run.py

test:
	@$(PYTHON) -m pytest -q -c config/pytest.ini

e2e:
	@$(PYTHON) -m pytest tests/e2e -q -m e2e -c config/pytest.ini

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
