FROM python:3.11-slim

WORKDIR /app

COPY ocpp16_min ./ocpp16_min
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen

ENV APP_HOST=0.0.0.0
ENV APP_PORT=9000

CMD ["uv", "run", "python", "-m", "ocpp16_min.server"]
