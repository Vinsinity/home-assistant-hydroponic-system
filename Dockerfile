FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GROWASIST_DATA_DIR=/data

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY growasist ./growasist
COPY custom_components ./custom_components
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --create-home growasist \
    && mkdir -p /data \
    && chown growasist:growasist /data

USER growasist
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=2)"

CMD ["growasist", "serve", "--host", "0.0.0.0", "--port", "8080"]
