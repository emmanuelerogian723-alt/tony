FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    TONY_DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tony ./tony
COPY scripts ./scripts
COPY pyproject.toml README.md ./

RUN mkdir -p /data && useradd -m -u 10001 tony && chown -R tony /app /data
USER tony

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/health',timeout=4)" || exit 1

CMD ["sh", "-c", "uvicorn tony.main:app --host 0.0.0.0 --port ${PORT}"]
