#!/bin/bash
echo "=== 架构检查 ==="
echo "1. 当前终端架构:"
arch
echo ""
echo "2. 系统默认 Python 架构:"
file $(which python3)
echo ""
echo "3. uv 使用的 Python:"
which python3
echo ""
echo "4. 虚拟环境 Python 架构（如果存在）:"
if [ -f backend/.venv/bin/python ]; then
    file backend/.venv/bin/python
else
    echo "虚拟环境不存在"
fi
echo ""
echo "5. 检查 Rosetta 状态:"
pkgutil --files com.apple.pkg.RosettaUpdateAuto 2>/dev/null | head -3 || echo "Rosetta 未安装或未查询到"
