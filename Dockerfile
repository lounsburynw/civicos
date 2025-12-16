# Civic Platform - Docker Image
# Multi-stage build for optimized image size
# Targets: REST API (8001) and WebSocket (8002) servers
#
# DATA ARCHITECTURE:
# - /app/bundled-data/ : Read-only reference data (vectors, events, legislative)
#                        Baked into image, updated on each deploy
# - /app/user-data/    : Persistent user data (participation DB, sessions)
#                        Mounted as Fly.io volume, never overwritten
#
# See docs/critical/DEPLOYMENT_GUIDE.md for details

# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

# Install build dependencies for native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install civic package
COPY packages/civic/pyproject.toml packages/civic/README.md /tmp/civic/
COPY packages/civic/src /tmp/civic/src
RUN pip install --no-cache-dir /tmp/civic[embeddings]

# Install civic-services package (application layer)
COPY packages/civic-services/pyproject.toml /tmp/civic-services/
COPY packages/civic-services/src /tmp/civic-services/src
RUN pip install --no-cache-dir /tmp/civic-services

# Stage 2: Runtime image
FROM python:3.11-slim AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash civic
WORKDIR /app

# Copy application code
COPY packages/ ./packages/

# Copy bundled data (events, vectors, legislative context)
# This is read-only reference data updated on each deploy
COPY data/pilot/ ./bundled-data/pilot/
COPY data/events/ ./bundled-data/events/
COPY data/legislative_context/ ./bundled-data/legislative_context/

# Create user data directory (will be mounted as volume in production)
# User data is persistent and never overwritten by deploys
RUN mkdir -p user-data && \
    chown -R civic:civic /app

# Switch to non-root user
USER civic

# Environment defaults
ENV CIVIC_ENV=production
ENV CIVIC_API_PORT=8001
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose ports for REST API and WebSocket
EXPOSE 8001 8002

# Health check using dedicated /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Default command: REST API server
CMD ["python", "-m", "civic_services.servers.civic_api_integrated"]
