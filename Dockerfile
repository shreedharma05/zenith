# Zenith app container
FROM python:3.12-slim

WORKDIR /app

# System deps for pdfplumber (needs libs for image/PDF handling)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Shell form (not exec form) so $PORT expands -- most PaaS hosts (Render,
# Railway, etc.) inject their own PORT env var instead of using a fixed one;
# docker-compose leaves PORT unset, so this still defaults to 8000 locally.
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
