#!/usr/bin/env bash
# 消息中继端到端测试编排脚本
#
# 职责：
#   1. 清理本地 SQLite 与 MC MySQL 的 evoloop 数据
#   2. 检查并启动 MySQL/Redis、MC PHP、Gateway、Backend API
#   3. 等待服务健康
#   4. 调用 Python 测试脚本发起多轮对话并验证同步
#
# 用法：
#   cd evoloop/backend
#   ./tests/run_message_relay_e2e.sh [--mode mock|real] [--turns N]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

EVOLOOP_BACKEND="${WORKSPACE}/evoloop/backend"
MEMBER_CENTER="${WORKSPACE}/member-center"
GATEWAY_DIR="${MEMBER_CENTER}/gateway"
MC_BACKEND_DIR="${MEMBER_CENTER}/backend"

GATEWAY_PORT=9001
MC_PHP_PORT=9002
BACKEND_API_PORT=20160
MYSQL_PORT=3306

MODE="mock"
TURNS=3
START_WORKER=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --turns)
      TURNS="$2"
      shift 2
      ;;
    --start-worker)
      START_WORKER=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

port_in_use() {
  local port="$1"
  nc -z 127.0.0.1 "$port" 2>/dev/null
}

wait_for_port() {
  local name="$1" port="$2" timeout="${3:-30}"
  log "Waiting for ${name} on port ${port}..."
  for ((i=0; i<timeout; i++)); do
    if port_in_use "$port"; then
      log "✓ ${name} ready"
      return 0
    fi
    sleep 1
  done
  log "✗ ${name} failed to start within ${timeout}s"
  return 1
}

# ==================== Cleanup ====================

cleanup_data() {
  log "Cleaning up local SQLite data..."
  sqlite3 ~/.evoloop/database/backend.db "DELETE FROM conversations; DELETE FROM messages;" || true
  log "Cleaning up MC MySQL evoloop data..."
  docker exec -i "$(docker ps --filter name=mysql -q)" mysql -uroot -padmin888 b2c_mall -e "
    SET FOREIGN_KEY_CHECKS = 0;
    TRUNCATE TABLE evoloop_messages;
    TRUNCATE TABLE evoloop_conversations;
    TRUNCATE TABLE evoloop_conversation_archives;
    TRUNCATE TABLE evoloop_message_references;
    TRUNCATE TABLE evoloop_file_operations;
    TRUNCATE TABLE evoloop_human_requests;
    TRUNCATE TABLE evoloop_agent_activities;
    TRUNCATE TABLE evoloop_push_logs;
    TRUNCATE TABLE evoloop_commands;
    SET FOREIGN_KEY_CHECKS = 1;
  " >/dev/null 2>&1 || true
  log "✓ Cleanup done"
}

# ==================== Services ====================

PIDS=()

cleanup_processes() {
  log "Stopping services started by this script..."
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup_processes EXIT

start_service() {
  local name="$1" cwd="$2" cmd="$3" logfile="$4"
  log "Starting ${name}..."
  mkdir -p "$(dirname "$logfile")"
  (cd "$cwd" && eval "$cmd" >"$logfile" 2>&1 &)
  PIDS+=("$!")
}

ensure_services() {
  # MySQL + Redis
  if ! port_in_use "$MYSQL_PORT"; then
    log "Starting MySQL + Redis via docker-compose..."
    (cd "$MEMBER_CENTER" && docker compose up -d mysql redis)
    wait_for_port "MySQL" "$MYSQL_PORT" 60
  fi

  # MC PHP
  if ! port_in_use "$MC_PHP_PORT"; then
    start_service "MC PHP" "$MC_BACKEND_DIR" "php -S 127.0.0.1:${MC_PHP_PORT} router.php" "/tmp/mc_php.log"
    wait_for_port "MC PHP" "$MC_PHP_PORT"
  fi

  # Gateway
  if ! port_in_use "$GATEWAY_PORT"; then
    start_service "Gateway" "$GATEWAY_DIR" "./gateway -config=./config.json" "/tmp/gateway.log"
    wait_for_port "Gateway" "$GATEWAY_PORT"
  fi

  # Backend API
  if ! port_in_use "$BACKEND_API_PORT"; then
    start_service "Backend API" "$EVOLOOP_BACKEND" "bash bin/evo dev" "/tmp/evoloop_api.log"
    wait_for_port "Backend API" "$BACKEND_API_PORT" 60
    log "Backend API starting up, waiting extra 10s for readiness..."
    sleep 10
  fi

  # Worker (optional)
  if [[ "$START_WORKER" == true ]] && ! pgrep -f "bin/run.py worker" >/dev/null; then
    start_service "Worker" "$EVOLOOP_BACKEND" "bash bin/evo worker" "/tmp/evoloop_worker.log"
    sleep 5
  fi
}

# ==================== Main ====================

main() {
  log "=============================================="
  log "Message Relay E2E Test Orchestration"
  log "=============================================="
  log "Mode: ${MODE}, Turns: ${TURNS}"

  ensure_services
  cleanup_data

  log "Running Python test script..."
  cd "$EVOLOOP_BACKEND"
  uv run python tests/run_message_relay_e2e_test.py --turns "$TURNS" --skip-service-check

  log "✅ E2E test orchestration completed"
}

main "$@"
