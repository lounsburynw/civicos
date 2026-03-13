FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install relay package from monorepo source
COPY packages/civicos-relay/pyproject.toml packages/civicos-relay/
COPY packages/civicos-relay/src/ packages/civicos-relay/src/

RUN pip install --no-cache-dir "packages/civicos-relay/[server,postgres]"

EXPOSE 8003

CMD ["civicos-relay"]
