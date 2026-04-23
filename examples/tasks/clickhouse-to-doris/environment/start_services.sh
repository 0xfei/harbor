#!/bin/bash
set -e

echo "=== Starting ClickHouse Server ==="
# ClickHouse 已在后台运行（FROM 基础镜像启动）

# 等待 ClickHouse 就绪
for i in {1..30}; do
    if clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
        echo "ClickHouse is ready"
        break
    fi
    sleep 1
done

echo "=== Starting Doris FE ==="
cd ${DORIS_HOME}/fe && ./bin/start_fe.sh --daemon

# 等待 FE 就绪
echo "Waiting for Doris FE..."
for i in {1..60}; do
    if nc -z 127.0.0.1 9030 2>/dev/null; then
        echo "Doris FE is ready"
        break
    fi
    sleep 1
done

echo "=== Starting Doris BE ==="
cd ${DORIS_HOME}/be && ./bin/start_be.sh --daemon

# 等待 BE 就绪
echo "Waiting for Doris BE..."
for i in {1..60}; do
    if nc -z 127.0.0.1 9050 2>/dev/null; then
        echo "Doris BE is ready"
        break
    fi
    sleep 1
done

# 注册 BE 到 FE
sleep 10
mysql -h127.0.0.1 -P9030 -uroot -e "ALTER SYSTEM ADD BACKEND '127.0.0.1:9050';" 2>/dev/null || true

echo "=== All Services Started ==="
echo "ClickHouse: localhost:9000 (native), localhost:8123 (HTTP)"
echo "Doris FE: localhost:9030 (MySQL protocol)"
echo "Doris BE: localhost:9050"

# 保持容器运行
tail -f /dev/null
