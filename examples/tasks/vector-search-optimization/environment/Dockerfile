FROM ubuntu:22.04

LABEL maintainer="hhxlovety@gmail.com"
LABEL description="C++ vector search optimization environment"

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install build tools and minimal Python for data conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    g++ \
    make \
    time \
    python3 \
    python3-pip \
    python3-numpy \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create directories
WORKDIR /app
RUN mkdir -p /data /logs/verifier

# Copy baseline and utility files (will be mounted at runtime)
# baseline.cpp, convert.py, Makefile should be in app/ directory

# Set environment
ENV CXX=g++
ENV CXXFLAGS="-std=c++11 -O2 -Wall"

CMD ["bash"]
