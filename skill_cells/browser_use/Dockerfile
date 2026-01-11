FROM mcr.microsoft.com/playwright:v1.49.0-jammy

# Install Python dependencies basic tools
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Source
COPY src/ ./src/

# Install dependencies from src
# Using pip to install the package in editable mode or just install deps
# We also need mcp, uvicorn, etc.
RUN pip install --no-cache-dir ./src
RUN pip install --no-cache-dir mcp uvicorn[standard] langchain-openai

# Copy server code
COPY server.py .

# Environment
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

EXPOSE 8000

# Start script
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
