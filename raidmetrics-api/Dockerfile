# =============================
# Base Image
# =============================

FROM python:3.11-slim AS base
WORKDIR /raidmetrics
COPY requirements.txt .
RUN pip install -r requirements.txt
# Install curl for container healthchecks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
COPY main.py .
COPY api ./api

# =============================
# Development Image
# =============================

FROM base AS dev
ENTRYPOINT ["python3", "main.py"]

# =============================
# Production Image
# =============================

FROM base AS prod
ENTRYPOINT ["python3", "main.py"]