FROM mcr.microsoft.com/playwright:v1.49.0-jammy

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Source
COPY src/ ./src/

# Install dependencies from src
# We specifically use the requirements from src to ensure compatibility
# Plus mcp and uvicorn for the server
RUN pip install --no-cache-dir ./src
RUN pip install --no-cache-dir mcp uvicorn[standard] 

# Copy server code
COPY server.py .

# Environment
ENV PYTHONUNBUFFERED=1
ENV CRAWL4AI_HEADLESS=true

EXPOSE 8000

# Start script
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
