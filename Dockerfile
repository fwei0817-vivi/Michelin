FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY data/menus ./data/menus
COPY data/profiles ./data/profiles
COPY data/fixtures ./data/fixtures
COPY data/prepared ./data/prepared
COPY --from=web /web/dist ./web/dist
EXPOSE 8000
CMD ["uvicorn", "michelin.api:app", "--host", "0.0.0.0", "--port", "8000"]
