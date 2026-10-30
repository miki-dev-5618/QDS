# syntax=docker/dockerfile:1
###############################################################################
# HEDWIG V2.2 - Quantum Digital Signature demo server
#
#   docker compose up --build      (app + PostgreSQL 15)
#   docker build -t hedwig . && docker run -p 8000:8000 hedwig   (SQLite only)
#
# Single process, single worker on purpose: server.py holds module-level
# in-process state (transmissions, sessions) guarded by an asyncio.Lock.
###############################################################################
FROM python:3.11-slim
 
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000
 
WORKDIR /app
 
# No compilers needed: qiskit-aer, cryptography and numpy all install from
# manylinux wheels on this base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
 
# --- dependencies (cached layer) --------------------------------------------
COPY requirements.txt requirements-pq.txt ./
ARG INSTALL_PQ=true
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_PQ" = "true" ]; then pip install -r requirements-pq.txt; fi
# cached layer
 
# --- application ------------------------------------------------------------
COPY . .
 
# Runtime-writable state: SQLite file + audit key. Everything else stays
# root-owned and read-only for the runtime user.
RUN groupadd --gid 10001 hedwig \
    && useradd --uid 10001 --gid hedwig --create-home --shell /usr/sbin/nologin hedwig \
    && mkdir -p /app/data \
    && chown -R hedwig:hedwig /app/data
 
USER hedwig
 
EXPOSE 8000
 
# /health is unauthenticated, so the probe needs no credentials.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4).status == 200 else 1)"
 
# exec -> uvicorn becomes PID 1 and receives SIGTERM for a clean shutdown.
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]