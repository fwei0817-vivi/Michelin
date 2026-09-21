FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY web ./web
COPY data/menus ./data/menus
COPY data/profiles ./data/profiles
COPY data/fixtures ./data/fixtures
EXPOSE 8000
CMD ["uvicorn", "michelin.api:app", "--host", "0.0.0.0", "--port", "8000"]
