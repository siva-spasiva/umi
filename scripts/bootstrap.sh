#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.local.yml"

echo "[1/4] Build and start services"
docker compose -f "$COMPOSE_FILE" up -d --build

echo "[2/4] Wait for API health"
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ "$i" -eq 60 ]]; then
    echo "API did not become healthy in time"
    exit 1
  fi
done

echo "[3/4] Initialize seed data"
docker compose -f "$COMPOSE_FILE" exec -T api python -m app.data.init_data

echo "[4/4] Done"
echo "API: http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
