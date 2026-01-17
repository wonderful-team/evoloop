FROM python:3.10-slim-bullseye

# Install system dependencies for Paddle and PyAutoGUI (X11)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    xvfb \
    x11-utils \
    scrot \
    python3-tk \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY server.py .
COPY start.sh .
RUN chmod +x start.sh

# Environment Variables
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

EXPOSE 8000

CMD ["./start.sh"]
