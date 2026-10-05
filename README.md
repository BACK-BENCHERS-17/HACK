# Hack Store bot

Run with Python 3.11 or newer:

```sh
pip install -r requirements.txt
bash start.sh
```

Set `BOT_TOKEN`, `ADMIN_IDS`, and `MONGO_URI` in your deployment's environment.
The database defaults to `hack_store_enterprise`; set `MONGO_DB_NAME` to override it.

## Configure payments directly in the bot

In a **private chat**, the owner opens **`/admin → UPI Session`**:

1. **Set UPI ID** — enter the receiving UPI address, such as `yourname@fam`.
2. **Payee Name** — enter the store/payee name shown on payment QRs.
3. **Connect / Change Gmail** — enter the account receiving FamApp credit
   alerts, followed by its 16-letter **Google App Password**. Spaces are accepted.
   Enable 2-Step Verification and create the App Password at
   <https://myaccount.google.com/apppasswords>.
4. **Mailbox** — defaults to `INBOX`. Select `[Gmail]/All Mail` if alerts are
   archived there.
5. **Test Connection / Refresh** — checks Gmail login/mailbox access and MongoDB,
   and shows which setup fields are missing.

The MongoDB line checks the bot's database connection. **Payment storage** is a
separate check for the SDK connection and required payment indexes/permissions.
A payment-storage error does not turn a working MongoDB connection into
`DISCONNECTED`.

The bot tests a new Gmail login before replacing the saved account. Settings
are stored in MongoDB and reloaded for QR creation and verification without a
restart. The password is encrypted using a key derived from `BOT_TOKEN`, and
its chat message is deleted when possible. Reconnect Gmail after rotating the
bot token. Passwords are never displayed in the panel or admin logs.

Only configured owners can view/change payment configuration; staff cannot.
Use **Cancel Process** or `/cancel` during setup to leave it unchanged.
`IMAP_USERNAME`, `IMAP_APP_PASSWORD`, `DEFAULT_UPI_ID`, and `DEFAULT_PAYEE_NAME`
remain optional environment fallbacks for older deployments; saved bot settings
take precedence. An App Password is required for Gmail IMAP, not a normal
Google account password.

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
