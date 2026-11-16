# Baseline NBA: API + web app in one container (AWS App Runner / ECS, Azure Container Apps, GCP Cloud Run, Render, Fly).
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 BASELINE_HOME=/var/baseline
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY engine/ engine/
COPY data/ data/
COPY --from=web /web/dist web/dist
RUN mkdir -p /var/baseline
VOLUME ["/var/baseline"]
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
