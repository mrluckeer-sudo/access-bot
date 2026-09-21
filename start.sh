#!/usr/bin/env bash
# Пример start-команды для PaaS (Render, Amvera и т.п.)
set -euo pipefail
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
