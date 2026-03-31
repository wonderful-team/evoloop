#!/bin/bash
# EvoLoop 测试监控系统启动脚本

cd "$(dirname "$0")/../.."

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        EvoLoop 测试监控系统                               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 Python3${NC}"
    exit 1
fi

# 检查依赖
echo "检查依赖..."
python3 -c "import httpx" 2>/dev/null || pip install httpx -q
python3 -c "import pytest" 2>/dev/null || pip install pytest pytest-asyncio -q

# 检查 API Key
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${YELLOW}警告: 未设置 OPENAI_API_KEY${NC}"
    echo "测试将跳过真实 LLM 调用部分"
fi

# 检查后端服务
echo "检查后端服务..."
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 后端服务运行中${NC}"
else
    echo -e "${YELLOW}⚠ 后端服务未检测到 (http://localhost:8000)${NC}"
    echo "请确保后端服务已启动: python -m app.main"
    echo ""
    read -p "是否继续? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 创建必要目录
mkdir -p tests/monitoring/{reports,logs}

# 菜单
while true; do
    echo ""
    echo "请选择操作:"
    echo "  1) 单场景测试（带监控）"
    echo "  2) 批量测试"
    echo "  3) 查看最近报告"
    echo "  4) 异常分析"
    echo "  5) 交互式修正"
    echo "  6) 趋势分析"
    echo "  0) 退出"
    echo ""
    read -p "选择: " choice

    case $choice in
        1)
            echo ""
            echo "可用场景:"
            echo "  code_generation, code_optimization, debugging"
            echo "  file_operation, knowledge_query, android_control"
            echo "  browser_automation, desktop_control, ambiguous"
            echo "  complex_task, dangerous_operation, multi_turn"
            echo "  reference_previous, edge_case"
            echo ""
            read -p "输入场景名称 (默认: code_generation): " scenario
            scenario=${scenario:-code_generation}
            read -p "最大轮次 (默认: 3): " rounds
            rounds=${rounds:-3}
            
            echo -e "\n${BLUE}启动测试: $scenario${NC}"
            python3 tests/monitoring/test_executor.py \
                --scenario "$scenario" \
                --max-rounds "$rounds"
            ;;
        
        2)
            echo ""
            read -p "场景 (逗号分隔, 或输入 'all'): " scenarios
            scenarios=${scenarios:-code_generation,debugging,knowledge_query}
            read -p "每场景轮次 (默认: 3): " rounds
            rounds=${rounds:-3}
            read -p "失败自动重试? (y/N): " retry
            
            retry_flag=""
            [[ $retry =~ ^[Yy]$ ]] && retry_flag="--retry"
            
            echo -e "\n${BLUE}启动批量测试...${NC}"
            python3 tests/monitoring/batch_runner.py \
                --scenarios "$scenarios" \
                --max-rounds "$rounds" \
                $retry_flag
            ;;
        
        3)
            echo ""
            echo -e "${BLUE}最近报告:${NC}"
            ls -lt tests/monitoring/reports/*.json 2>/dev/null | head -5 | awk '{print "  " $9}'
            ;;
        
        4)
            echo ""
            python3 tests/monitoring/anomaly_analyzer.py --latest
            ;;
        
        5)
            echo ""
            python3 tests/monitoring/batch_runner.py --interactive
            ;;
        
        6)
            echo ""
            read -p "分析天数 (默认: 7): " days
            days=${days:-7}
            python3 tests/monitoring/anomaly_analyzer.py --trend --days "$days"
            ;;
        
        0)
            echo "退出"
            exit 0
            ;;
        
        *)
            echo -e "${RED}无效选择${NC}"
            ;;
    esac
done
