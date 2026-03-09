FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[server]"

EXPOSE 8850

CMD ["civicos-signer", "serve", "--env-file", "/config/.env.signer"]
