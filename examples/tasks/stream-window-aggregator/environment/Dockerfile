FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    python3 \
    python3-pip \
    binutils \
    procps \
    time \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install pytest

# Pre-create required directories
RUN mkdir -p /app /data /logs/verifier

WORKDIR /app
