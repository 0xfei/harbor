#!/bin/bash
# 本地测试脚本 - 使用 Docker Compose 启动环境并运行测试

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== ClickHouse to Doris Migration Test ==="
echo "Task directory: $TASK_DIR"

# 检查 Docker Compose 是否可用
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "Error: docker-compose or docker compose not found"
    exit 1
fi

# 使用 docker compose 或 docker-compose
COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null; then
    COMPOSE_CMD="docker-compose"
fi

cd "$TASK_DIR/environment"

echo ""
echo "=== Step 1: Starting Services ==="
$COMPOSE_CMD up -d

echo ""
echo "=== Step 2: Waiting for Services to be Ready ==="
echo "Waiting for ClickHouse..."
for i in {1..60}; do
    if docker exec ch-server clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
        echo "ClickHouse is ready"
        break
    fi
    sleep 2
done

echo "Waiting for Doris FE..."
for i in {1..60}; do
    if docker exec doris-fe mysql -h127.0.0.1 -P9030 -uroot -e "SELECT 1" >/dev/null 2>&1; then
        echo "Doris FE is ready"
        break
    fi
    sleep 2
done

echo "Waiting for Doris BE..."
sleep 10

# 注册 BE 到 FE
echo "Registering BE to FE..."
docker exec doris-fe mysql -h127.0.0.1 -P9030 -uroot -e "ALTER SYSTEM ADD BACKEND 'doris-be:9050';" 2>/dev/null || true

echo ""
echo "=== Step 3: Running Migration Script ==="
docker exec test-runner bash /solution/solve.sh

echo ""
echo "=== Step 4: Running Verification Tests ==="
docker exec test-runner python3 /tests/verify_migration.py

echo ""
echo "=== Step 5: Running Benchmark ==="
docker exec test-runner python3 /app/benchmark.py

echo ""
echo "=== Test Complete ==="
echo "Logs available in: $TASK_DIR/environment/test_logs"

# 清理
read -p "Stop services? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    $COMPOSE_CMD down -v
fi
