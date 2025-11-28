FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=5000

# Install minimal system deps required for many Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \ 
      build-essential git curl && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose default port
EXPOSE 5000

# Start uvicorn (honors $PORT at runtime)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-5000}
