FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen

COPY server.py .

ENV APP_HOST=0.0.0.0
ENV APP_PORT=8765

CMD ["uv", "run", "python", "server.py"]
