#!/usr/bin/env bash
# Production launcher
set -e

echo "[start.sh] Starting Payment Service..."
python payment_service.py &
SVC_PID=$!

echo "[start.sh] Waiting for service to bind..."
sleep 5

echo "[start.sh] Starting Bot..."
python bot.py &
BOT_PID=$!

# Wait for processes
wait -n

# If any process dies, kill the other and exit
kill $SVC_PID $BOT_PID 2>/dev/null || true
