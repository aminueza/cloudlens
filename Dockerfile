FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .
COPY config/ config/
COPY providers/ providers/
COPY graph/ graph/
COPY exporters/ exporters/
COPY api/ api/
COPY db/ db/
COPY engine/ engine/
COPY ai/ ai/
COPY templates/ templates/
COPY static/ static/
COPY main.py .

RUN pip install --no-cache-dir ".[all-providers]"

RUN mkdir -p /app/data

EXPOSE 8050

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8050/health || exit 1

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8050"]
