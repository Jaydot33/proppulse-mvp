FROM python:3.11-slim

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Expose port
EXPOSE $PORT

# Start
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "${PORT:-5000}"]
