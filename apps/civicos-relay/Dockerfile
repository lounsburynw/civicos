FROM python:3.11-slim

LABEL org.opencontainers.image.title="CivicOS Relay" \
      org.opencontainers.image.description="Federation-ready civic coordination relay" \
      org.opencontainers.image.source="https://github.com/lounsburynw/civicos"

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Non-root user for production security
RUN useradd --create-home --shell /bin/bash relay

WORKDIR /app

# Install relay package from monorepo source
COPY packages/civicos-relay/pyproject.toml packages/civicos-relay/
COPY packages/civicos-relay/src/ packages/civicos-relay/src/

RUN pip install --no-cache-dir "packages/civicos-relay/[server,postgres]"

# Create directory for relay keys (mount as volume for persistence)
RUN mkdir -p /secrets && chown relay:relay /secrets

USER relay

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

CMD ["civicos-relay"]
