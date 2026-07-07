# Thin root wrapper — all targets live in src/Makefile
export COMPOSE_FILE := src/docker/compose.yml
export PYTHONPATH := $(CURDIR)/src

.PHONY: setup quick install start stop smoke preflight dev test e2e locales screenshot publish-check docker-up docker-down docker-logs clean

setup quick install start stop smoke preflight dev test e2e locales screenshot publish-check docker-up docker-down docker-logs clean:
	@$(MAKE) -C src -f Makefile $@
