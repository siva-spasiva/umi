COMPOSE_FILE := docker-compose.local.yml

.PHONY: up down restart logs ps seed bootstrap config

up:
	docker compose -f $(COMPOSE_FILE) up -d --build

down:
	docker compose -f $(COMPOSE_FILE) down

restart:
	docker compose -f $(COMPOSE_FILE) down
	docker compose -f $(COMPOSE_FILE) up -d --build

logs:
	docker compose -f $(COMPOSE_FILE) logs -f api

ps:
	docker compose -f $(COMPOSE_FILE) ps

seed:
	docker compose -f $(COMPOSE_FILE) exec -T api python -m app.data.init_data

bootstrap:
	./scripts/bootstrap.sh

config:
	docker compose -f $(COMPOSE_FILE) config
