# ── Stage 1: Build Frontend ──
FROM node:20-slim AS frontend-builder
WORKDIR /app
COPY app/package*.json ./
RUN npm ci
COPY app/ ./
RUN npm run build

# ── Stage 2: Production Python & FFmpeg ──
FROM python:3.10-slim
WORKDIR /workspace

# Install system dependencies (FFmpeg, ffprobe, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY impl/ ./impl/

# Copy built frontend assets from Stage 1 into app/dist
COPY --from=frontend-builder /app/dist ./app/dist

# Expose port (Cloud providers like Render/Railway pass $PORT, default 8080)
ENV PORT=8080
EXPOSE 8080

CMD ["python3", "impl/api_server.py"]
