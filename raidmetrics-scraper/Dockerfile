FROM python:3.10-slim AS base

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY scraper ./scraper

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
