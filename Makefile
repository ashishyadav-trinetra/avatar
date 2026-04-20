.PHONY: help \
        dev dev-build dev-stop dev-logs dev-restart \
        prod prod-build prod-stop prod-logs prod-restart \
        setup-dev setup-prod \
        gpu-check clean shell-% logs-%

# ─────────────────────────────────────────────────────────────
#  AI Avatar POC — Makefile
#  Two modes: dev (CPU, stub renderer) and prod (GPU, MuseTalk)
# ─────────────────────────────────────────────────────────────

DC_DEV  = docker compose -f docker-compose.dev.yml
DC_PROD = docker compose -f docker-compose.prod.yml

help:
	@echo ""
	@echo "  AI Avatar POC"
	@echo "  ══════════════════════════════════════════════════"
	@echo "  DEVELOPMENT (no GPU needed)"
	@echo "    make setup-dev   — first-time dev setup"
	@echo "    make dev         — start dev stack"
	@echo "    make dev-stop    — stop dev stack"
	@echo "    make dev-logs    — tail dev logs"
	@echo "    make dev-build   — rebuild dev images"
	@echo ""
	@echo "  PRODUCTION (GPU required)"
	@echo "    make setup-prod  — download models + build prod images"
	@echo "    make prod        — start prod stack"
	@echo "    make prod-stop   — stop prod stack"
	@echo "    make prod-logs   — tail prod logs"
	@echo "    make prod-build  — rebuild prod images"
	@echo ""
	@echo "  UTILITIES"
	@echo "    make gpu-check   — verify NVIDIA GPU accessible"
	@echo "    make clean       — remove all containers + images"
	@echo "    make shell-<svc> — bash into a running container"
	@echo "    make logs-<svc>  — tail one service log"
	@echo "  ══════════════════════════════════════════════════"
	@echo ""

# ─────────────────────────────────────────────────────────────
#  DEVELOPMENT
# ─────────────────────────────────────────────────────────────

setup-dev:
	@echo "── Dev setup ──"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✓ Created .env — fill in LIVEKIT_* and OPENAI_API_KEY"; \
	else \
		echo "✓ .env already exists"; \
	fi
	@echo "── Building dev images (CPU only, ~3 min) ──"
	$(DC_DEV) build
	@echo ""
	@echo "✓ Dev setup complete."
	@echo "  1. Edit .env with your API credentials"
	@echo "  2. Run: make dev"
	@echo "  3. Open: http://localhost:3000"
	@echo ""
	@echo "  NOTE: Dev mode uses a stub renderer instead of MuseTalk."
	@echo "  You will see 'DEV MODE' watermark on the avatar — this is expected."
	@echo "  The full lip-sync pipeline runs; only the renderer is mocked."

dev:
	@echo "── Starting dev stack ──"
	$(DC_DEV) up -d
	@echo ""
	@echo "✓ Dev stack running"
	@echo "  Frontend:    http://localhost:3000"
	@echo "  API Gateway: http://localhost:8000"
	@echo "  Redis:       localhost:6379 (exposed in dev)"
	@echo ""
	@echo "Tip: make dev-logs   to watch all output"

dev-stop:
	$(DC_DEV) down

dev-logs:
	$(DC_DEV) logs -f

dev-restart:
	$(DC_DEV) down
	$(DC_DEV) up -d

dev-build:
	$(DC_DEV) build --no-cache

# ─────────────────────────────────────────────────────────────
#  PRODUCTION
# ─────────────────────────────────────────────────────────────

setup-prod:
	@echo "── Production setup ──"
	@echo "── Step 1: Checking GPU ──"
	@docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi \
		|| (echo "✗ GPU not accessible. Install nvidia-docker2 first." && exit 1)
	@echo "── Step 2: Creating .env.prod ──"
	@if [ ! -f .env.prod ]; then \
		cp .env.example .env.prod; \
		echo "✓ Created .env.prod — fill in your credentials"; \
	else \
		echo "✓ .env.prod already exists"; \
	fi
	@echo "── Step 3: Downloading model weights (~3.5GB) ──"
	@bash scripts/download_models.sh
	@echo "── Step 4: Building prod images (~10 min) ──"
	$(DC_PROD) --env-file .env.prod build
	@echo ""
	@echo "✓ Prod setup complete."
	@echo "  1. Edit .env.prod with your API credentials"
	@echo "  2. Run: make prod"

prod:
	@echo "── Starting production stack ──"
	$(DC_PROD) --env-file .env.prod up -d
	@echo ""
	@echo "✓ Production stack running"
	@echo "  Frontend:      http://localhost:3000"
	@echo "  API Gateway:   http://localhost:8000"
	@echo "  WebRTC Bridge: http://localhost:8002"
	@echo ""
	@echo "Avatar engine startup takes ~60-90s (loading GPU models)"
	@echo "Run: make prod-logs  to watch progress"

prod-stop:
	$(DC_PROD) --env-file .env.prod down

prod-logs:
	$(DC_PROD) --env-file .env.prod logs -f

prod-restart:
	$(DC_PROD) --env-file .env.prod down
	$(DC_PROD) --env-file .env.prod up -d

prod-build:
	$(DC_PROD) --env-file .env.prod build --no-cache

# ─────────────────────────────────────────────────────────────
#  UTILITIES
# ─────────────────────────────────────────────────────────────

gpu-check:
	@echo "── Checking NVIDIA GPU ──"
	@docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi \
		&& echo "✓ GPU accessible" \
		|| echo "✗ GPU not accessible — check nvidia-docker2 installation"

clean:
	@echo "── Cleaning up dev + prod ──"
	-$(DC_DEV) down -v --rmi local 2>/dev/null
	-$(DC_PROD) down -v --rmi local 2>/dev/null
	@echo "✓ Cleaned"

# shell into any running container: make shell-avatar-engine
shell-%:
	@$(DC_DEV) exec $* /bin/bash 2>/dev/null || $(DC_PROD) exec $* /bin/bash

# tail one service: make logs-avatar-engine
logs-%:
	@$(DC_DEV) logs -f $* 2>/dev/null || $(DC_PROD) logs -f $*
