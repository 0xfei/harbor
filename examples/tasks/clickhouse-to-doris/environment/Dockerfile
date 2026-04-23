# ClickHouse to Doris Migration Task
# 简化版 Dockerfile - 仅包含客户端工具
# 数据库服务需要通过 docker-compose 或外部提供

FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# 安装 MySQL 客户端（用于连接 Doris）和基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    curl procps netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
RUN pip install --no-cache-dir pymysql clickhouse-driver pytest

# 创建工作目录
RUN mkdir -p /app /data /logs/verifier /tests

WORKDIR /app

# 复制应用代码
COPY app/ /app/

# 默认命令
CMD ["bash", "-c", "echo 'Environment ready. Connect to external CH/Doris services.'"]
