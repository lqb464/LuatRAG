FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY src ./src
COPY data/legal-corpus.json ./data/legal-corpus.json
RUN pip install . && useradd --create-home --uid 10001 appuser && mkdir -p /data && chown appuser:appuser /data
ENV LUATRAG_DATA_DIR=/data
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
