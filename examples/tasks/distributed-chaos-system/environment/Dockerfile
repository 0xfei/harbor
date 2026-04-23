FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir psutil pytest

WORKDIR /app

# 创建必要目录
RUN mkdir -p /data /logs/verifier /tests
