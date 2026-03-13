#!/bin/bash
# start_dev.sh - 一键启动开发环境

cd "$(dirname "$0")"

echo "=== 编译 Recorder ==="
cd frontend/src-tauri
cargo build --bin recorder 2>/dev/null || echo "编译失败，请检查 Rust 环境"
cd ../../..

echo ""
echo "=== 启动后端 ==="
cd backend
source .venv/bin/activate
python -m app.main &
BACKEND_PID=$!
cd ..

echo ""
echo "=== 等待后端启动 (5秒) ==="
sleep 5

echo ""
echo "=== 启动前端 ==="
cd frontend/packages/desktop
pnpm tauri dev &
FRONTEND_PID=$!
cd ../../..

echo ""
echo "=== 开发环境已启动 ==="
echo "后端: http://localhost:8000"
echo "前端: 正在启动..."
echo ""
echo "按 Ctrl+C 停止所有服务"

# 清理函数
cleanup() {
    echo ""
    echo "=== 停止服务 ==="
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}
trap cleanup INT

wait
