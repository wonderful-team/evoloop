FROM python:3.10-slim-bullseye

# Install system dependencies
# ADB is crucial here
RUN apt-get update && apt-get install -y \
    android-tools-adb \
    gcc \
    python3-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Source
COPY src/ ./src/

# Install dependencies
# Open-AutoGLM requires some packages.
# We also install 'mcp' and 'uvicorn' for the wrapper.
RUN pip install --no-cache-dir ./src
RUN pip install --no-cache-dir mcp uvicorn[standard]

# Copy server code
COPY server.py .

# Environment
ENV PYTHONUNBUFFERED=1
# Default ADB server socket if using host routing (optional)
# ENV ADB_SERVER_SOCKET=tcp:host.docker.internal:5037

EXPOSE 8000

# Start script
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
