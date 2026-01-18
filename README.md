# laughing-octo-guacamole

Minimal OCPP 1.6-J BootNotification exchange (happy path only) between a
charge point emulator and a server over WebSockets.

## Prerequisites

- Python 3.10+
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
sends one StatusNotification (Available), then StartTransaction and
StopTransaction (after ~10 seconds). Heartbeats run during the
simulated session and MeterValues are sent every 5 seconds. Exits with
code 0 only on success.

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
INFO - Received raw: [2,"...","StatusNotification",{"connectorId":0,"status":"Available","errorCode":"NoError",...}]
INFO - Parsed CALL: action=StatusNotification uid=...
INFO - StatusNotification: connectorId=0 status=Available
INFO - Sent: [3,"... ",{}]
INFO - Received raw: [2,"...","StartTransaction",{"connectorId":1,"idTag":"TEST","meterStart":0,"timestamp":"..."}]
INFO - Parsed CALL: action=StartTransaction uid=...
INFO - StartTransaction: chargePointId=CP_1 transactionId=1
INFO - Sent: [3,"... ",{"transactionId":1,"idTagInfo":{"status":"Accepted"}}]
INFO - Received raw: [2,"...","Heartbeat",{}]
INFO - Parsed CALL: action=Heartbeat uid=...
INFO - Sent: [3,"... ",{"currentTime":"2026-01-18T12:35:06Z"}]
INFO - Received raw: [2,"...","MeterValues",{"connectorId":1,"transactionId":1,"meterValue":[...]}]
INFO - Parsed CALL: action=MeterValues uid=...
INFO - MeterValues: chargePointId=CP_1 connectorId=1 transactionId=1 timestamp=... value=100
INFO - Sent: [3,"... ",{}]
INFO - Received raw: [2,"...","MeterValues",{"connectorId":1,"transactionId":1,"meterValue":[...]}]
INFO - Parsed CALL: action=MeterValues uid=...
INFO - MeterValues: chargePointId=CP_1 connectorId=1 transactionId=1 timestamp=... value=200
INFO - Sent: [3,"... ",{}]
INFO - Received raw: [2,"...","StopTransaction",{"transactionId":1,"meterStop":200,"timestamp":"...","reason":"Local","idTag":"TEST"}]
INFO - Parsed CALL: action=StopTransaction uid=...
INFO - StopTransaction: transactionId=1 meterStop=200
INFO - Sent: [3,"... ",{"idTagInfo":{"status":"Accepted"}}]
INFO - Client disconnected: CP_1
```

**Client**
```
RAW RESPONSE: [3,"... ",{"status":"Accepted","currentTime":"2026-01-18T12:34:56Z","interval":10}]
PARSED RESPONSE: {'status': 'Accepted', 'currentTime': '2026-01-18T12:34:56Z', 'interval': 10}
StatusNotification sent (Available)
RAW RESPONSE: [3,"... ",{}]
PARSED RESPONSE: {}
StatusNotification acknowledged
StartTransaction sent (connectorId=1)
RAW RESPONSE: [3,"... ",{"transactionId":1,"idTagInfo":{"status":"Accepted"}}]
PARSED RESPONSE: {'transactionId': 1, 'idTagInfo': {'status': 'Accepted'}}
StartTransaction acknowledged (transactionId=1)
Heartbeat 1 sent
RAW RESPONSE: [3,"... ",{"currentTime":"2026-01-18T12:35:06Z"}]
PARSED RESPONSE: {'currentTime': '2026-01-18T12:35:06Z'}
Heartbeat 1 acknowledged
MeterValues sent (energy_wh=100)
RAW RESPONSE: [3,"... ",{}]
PARSED RESPONSE: {}
MeterValues acknowledged
MeterValues sent (energy_wh=200)
RAW RESPONSE: [3,"... ",{}]
PARSED RESPONSE: {}
MeterValues acknowledged
StopTransaction sent (transactionId=1)
RAW RESPONSE: [3,"... ",{"idTagInfo":{"status":"Accepted"}}]
PARSED RESPONSE: {'idTagInfo': {'status': 'Accepted'}}
StopTransaction acknowledged (transactionId=1)
```