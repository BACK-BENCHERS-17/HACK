#!/usr/bin/env bash
# Production launcher: runs the payment microservice and the Telegram bot
# together inside the same VM/process group.
set -e

cleanup() {
  echo "[start.sh] shutting down…"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python payment_service.py &
SVC_PID=$!
echo "[start.sh] payment_service started (pid=$SVC_PID)"

# Give the service a moment to bind its port before the bot makes any calls.
sleep 2

python bot.py &
BOT_PID=$!
echo "[start.sh] bot started (pid=$BOT_PID)"

# Exit (and trigger cleanup) as soon as either child exits.
wait -n
