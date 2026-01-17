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

# Copy and install explicit comprehensive requirements
COPY requirements_final.txt .
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir -r requirements_final.txt

# Install the package itself
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir --no-deps ./src 

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
