# Hack Store bot

Run with Python 3.11 or newer:

```sh
pip install -r requirements.txt
bash start.sh
```

Set `BOT_TOKEN`, `ADMIN_IDS`, `MONGO_URI`, `IMAP_USERNAME`, and
`IMAP_APP_PASSWORD` in your deployment's environment. The database defaults to
`hack_store_enterprise`; set `MONGO_DB_NAME` to override it. Configure the payee
UPI ID in the bot's admin panel.

## Render deployment

The supplied `render.yaml` defines a **Web Service** with:

- Start command: `bash start.sh`
- Health check path: `/healthz`
- Listener: `0.0.0.0:$PORT` (Render supplies `PORT`)

When updating an existing service manually, set its health check path to
`/healthz` in the Render dashboard. The endpoint starts before Telegram polling
and stays available during retry/standby. This allows Render to finish the
deployment and terminate the old process. `start.sh` uses `exec` to forward
Render's shutdown signals directly to Python.

`/healthz` is a process-liveness check. `/readyz` returns 200 only once this
instance has successfully polled Telegram; it returns 503 while in standby.
**Use `/healthz` for Render's deploy check**, because the new instance may need
to wait for the old instance to stop before taking over polling.

Updated instances sharing the same Mongo database coordinate through one
`bot_runtime` lease document per bot ID. Only the owner calls `getUpdates`.
Ownership is checked before every poll, released after shutdown, and expires
after 90 seconds if the owner crashes. A standby instance keeps serving health
checks while waiting. The lease contains an instance identifier, bot ID, and
expiration time; no bot token is stored there.

Keep one intended deployment per bot token. An older bot version, another
service using a different database, or an external script does not participate
in this lease and must be stopped if `409 Conflict` continues. Worker/local
deployments also work: omit `PORT` to run without the HTTP listener.

## Tests

```sh
pip install -r requirements-dev.txt
python -W error::RuntimeWarning -m unittest discover -s tests -v
```

The tests exercise PTB polling/retry shutdown, Render health responses,
lease contention and expiry, and signal handling. Telegram responses and Mongo
data are simulated; the tests do not use production credentials.
