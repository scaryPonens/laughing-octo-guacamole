#!/usr/bin/env python3
"""
Simple WebSocket server that logs incoming messages and replies with static JSON.
"""
import asyncio
import json
import logging
import os
import atexit
import websockets
from opentelemetry import trace, propagate
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# OpenTelemetry setup
def setup_tracing():
    service_name = os.getenv("OTEL_SERVICE_NAME", "websocket-server")
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


tracer = trace.get_tracer(__name__)

# Static JSON response
STATIC_RESPONSE = {
    "status": "ok",
    "message": "Message received",
    "server": "websocket-demo"
}


async def handle_client(websocket):
    """
    Handle incoming WebSocket connections.
    
    Logs all incoming messages verbatim and replies with static JSON.
    """
    client_address = websocket.remote_address
    logger.info(f"Client connected from {client_address}")
    
    try:
        request_headers = getattr(websocket, "request_headers", None)
        if request_headers is None:
            request = getattr(websocket, "request", None)
            request_headers = getattr(request, "headers", None)
        if request_headers is None:
            request_headers = {}

        parent_context = propagate.extract(request_headers)
        with tracer.start_as_current_span(
            "ws.connection",
            context=parent_context,
        ) as span:
            span.set_attribute("ws.client", str(client_address))

            async for message in websocket:
                with tracer.start_as_current_span("ws.message") as msg_span:
                    msg_span.set_attribute("ws.message_length", len(message))

                    # Log the incoming message verbatim
                    logger.info(f"Received message: {message}")
                    msg_span.add_event("message.received")

                    # Reply with static JSON message
                    response = json.dumps(STATIC_RESPONSE)
                    await websocket.send(response)
                    logger.info(f"Sent response: {response}")
                    msg_span.add_event("message.sent")
            
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client {client_address} disconnected")
    except Exception as e:
        logger.error(f"Error handling client {client_address}: {e}")
    finally:
        logger.info(f"Connection closed for {client_address}")


async def main():
    """Start the WebSocket server."""
    setup_tracing()
    logger.addHandler(SpanEventHandler())
    host = os.getenv("APP_HOST", "localhost")
    port = int(os.getenv("APP_PORT", "8765"))
    
    logger.info(f"Starting WebSocket server on ws://{host}:{port}")
    
    async with websockets.serve(handle_client, host, port):
        logger.info("Server is running. Press Ctrl+C to stop.")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
