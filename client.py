#!/usr/bin/env python3
"""
Simple WebSocket client that connects to a server, sends a JSON payload, and prints the response.
"""
import asyncio
import json
import os
import atexit
import logging
import websockets
from opentelemetry import trace, propagate
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Hardcoded JSON payload to send
PAYLOAD = {
    "action": "test",
    "data": {
        "user": "demo",
        "timestamp": "2024-01-17T12:00:00Z",
        "message": "Hello from WebSocket client"
    }
}

# OpenTelemetry setup
def setup_tracing():
    service_name = os.getenv("OTEL_SERVICE_NAME", "websocket-client")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Ensure spans flush on shutdown
    atexit.register(provider.shutdown)


class SpanEventHandler(logging.Handler):
    def emit(self, record):
        span = trace.get_current_span()
        if span and span.is_recording():
            span.add_event(
                "log",
                {
                    "log.level": record.levelname,
                    "log.message": record.getMessage(),
                    "log.logger": record.name,
                },
            )


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

tracer = trace.get_tracer(__name__)


async def main():
    """Connect to WebSocket server, send message, receive response, and exit."""
    setup_tracing()
    logger.addHandler(SpanEventHandler())
    host = os.getenv("APP_HOST", "localhost")
    port = int(os.getenv("APP_PORT", "8765"))
    uri = f"ws://{host}:{port}"
    
    logger.info("Connecting to %s...", uri)
    
    try:
        carrier = {}
        with tracer.start_as_current_span("ws.client"):
            propagate.inject(carrier)
            connect_kwargs = {"additional_headers": carrier}
            try:
                connect_ctx = websockets.connect(uri, **connect_kwargs)
            except TypeError:
                connect_ctx = websockets.connect(uri, extra_headers=carrier)

            async with connect_ctx as websocket:
                logger.info("Connected!")

                # Send the hardcoded JSON payload
                message = json.dumps(PAYLOAD)
                logger.info("Sending: %s", message)
                await websocket.send(message)

                # Receive and print the response
                response = await websocket.recv()
                logger.info("Received: %s", response)
            
            # Parse and pretty-print the response
            try:
                response_data = json.loads(response)
                logger.info("Parsed response:\n%s", json.dumps(response_data, indent=2))
            except json.JSONDecodeError:
                logger.warning("Response is not valid JSON")
            
            logger.info("Connection closed.")
            
    except ConnectionRefusedError:
        logger.error("Could not connect to the server. Is it running?")
    except Exception as e:
        logger.error("Error: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
