FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir psutil pytest

WORKDIR /app

# Harbor 会在运行时挂载 app/, tests/, data/ 等目录
RUN mkdir -p /data /logs/verifier /tests
