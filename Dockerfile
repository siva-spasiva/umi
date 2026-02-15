# Base image with PyTorch and CUDA support
FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime

# Set working directory
WORKDIR /app

# Install system dependencies
# (git is often needed for pip installing from git repos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip
# Install heavy ML libs separately to avoid dependency resolution too deep
RUN pip install --no-cache-dir \
    "transformers>=4.38.2" \
    "accelerate>=0.27.2" \
    "bitsandbytes>=0.42.0" \
    "sentence-transformers>=2.5.1"

RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for logs
RUN mkdir -p logs

# Expose ports for API (8000) and GPU Server (8001)
EXPOSE 8000 8001

# Default command (overridden by docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
