FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and default config
COPY src/ /app/src/
COPY config/ /app/config/

# Create data directory for SQLite database persistence
RUN mkdir -p /app/data

# Expose web dashboard port
EXPOSE 8050

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8050/api/live || exit 1

# Launch monitor daemon and web UI
CMD ["python", "-m", "src.main"]
