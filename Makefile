PYTHON ?= python3.9
export PYTHONPATH := $(CURDIR)/src

.PHONY: setup quick install start stop smoke preflight dev test e2e locales screenshot publish-check docker-up docker-down docker-logs clean

setup:
	@chmod +x src/scripts/setup.sh src/scripts/install.sh src/scripts/start.sh src/scripts/stop.sh src/scripts/smoke_local.sh && ./src/scripts/setup.sh

quick: install start

install:
	@chmod +x src/scripts/install.sh && ./src/scripts/install.sh

start:
	@chmod +x src/scripts/start.sh && ./src/scripts/start.sh

stop:
	@chmod +x src/scripts/stop.sh && ./src/scripts/stop.sh

smoke:
	@chmod +x src/scripts/smoke_local.sh && ./src/scripts/smoke_local.sh

dev:
	@test -d .venv || $(PYTHON) -m venv .venv
	@. .venv/bin/activate && pip install -q -r src/config/requirements.txt
	@cd src/whatsapp-bridge && npm install --silent
	@. .venv/bin/activate && $(PYTHON) src/scripts/run.py

test:
	@$(PYTHON) -m pytest -q -c src/config/pytest.ini

e2e:
	@$(PYTHON) -m pytest src/tests/e2e -q -c src/config/pytest.ini -m e2e

locales:
	@$(PYTHON) src/scripts/validate_locales.py

screenshot:
	@$(PYTHON) src/scripts/capture_screenshot.py

preflight:
	@chmod +x src/scripts/preflight_public.sh && ./src/scripts/preflight_public.sh

publish-check: locales test
	@node --check src/whatsapp-bridge/server.js
	@./src/scripts/prepare_github.sh

docker-up:
	@docker compose up -d --build

docker-down:
	@docker compose down

docker-logs:
	@docker compose logs -f panel

clean:
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache
