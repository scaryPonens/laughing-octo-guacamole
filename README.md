# laughing-octo-guacamole

Minimal OCPP 1.6-J BootNotification exchange (happy path only) between a
charge point emulator and a server over WebSockets.

## Prerequisites

- Python 3.11+
- `uv` (https://docs.astral.sh/uv/)

## Setup (uv)

```bash
uv venv
uv sync
```

## Run

### Terminal 1: server

```bash
uv run python -m ocpp16_min.server
```

Server listens on `ws://localhost:9000/{chargePointId}`.

### Terminal 2: client

```bash
uv run python -m ocpp16_min.client
```

Client connects to `ws://localhost:9000/CP_1`, sends a BootNotification,
prints the response, and exits with code 0 only if it receives `Accepted`.

## Tracing (OpenTelemetry + Jaeger)

This project emits traces via OpenTelemetry OTLP. Client and server propagate
trace context over WebSockets, so spans appear in one distributed trace.

Environment variables:
- `OTEL_SERVICE_NAME` (default: `ocpp16-server` for server, `ocpp16-client` for client)
- `OTEL_EXPORTER_OTLP_ENDPOINT` (default: `http://localhost:4317`)

To run Jaeger locally:
```bash
docker compose up --build
```

## Expected Output (brief)

**Server**
```
INFO - Client connected: CP_1
INFO - Received raw: [2,"...","BootNotification",{"chargePointVendor":"RalphCo",...}]
INFO - Parsed CALL: action=BootNotification uid=...
INFO - Sent: [3,"... ",{"status":"Accepted","currentTime":"2026-01-18T12:34:56Z","interval":10}]
INFO - Received raw: [2,"...","Heartbeat",{}]
INFO - Parsed CALL: action=Heartbeat uid=...
INFO - Sent: [3,"... ",{"currentTime":"2026-01-18T12:35:06Z"}]
INFO - Received raw: [2,"...","Heartbeat",{}]
INFO - Parsed CALL: action=Heartbeat uid=...
INFO - Sent: [3,"... ",{"currentTime":"2026-01-18T12:35:16Z"}]
INFO - Received raw: [2,"...","Heartbeat",{}]
INFO - Parsed CALL: action=Heartbeat uid=...
INFO - Sent: [3,"... ",{"currentTime":"2026-01-18T12:35:26Z"}]
INFO - Client disconnected: CP_1
```

**Client**
```
RAW RESPONSE: [3,"... ",{"status":"Accepted","currentTime":"2026-01-18T12:34:56Z","interval":10}]
PARSED RESPONSE: {'status': 'Accepted', 'currentTime': '2026-01-18T12:34:56Z', 'interval': 10}
RAW RESPONSE: [3,"... ",{"currentTime":"2026-01-18T12:35:06Z"}]
PARSED RESPONSE: {'currentTime': '2026-01-18T12:35:06Z'}
RAW RESPONSE: [3,"... ",{"currentTime":"2026-01-18T12:35:16Z"}]
PARSED RESPONSE: {'currentTime': '2026-01-18T12:35:16Z'}
RAW RESPONSE: [3,"... ",{"currentTime":"2026-01-18T12:35:26Z"}]
PARSED RESPONSE: {'currentTime': '2026-01-18T12:35:26Z'}
```