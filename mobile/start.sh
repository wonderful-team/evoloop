#!/bin/bash
# EvoLoop Mobile 启动脚本
# 解决中文路径导致的 HTTP Header 错误

export EXPO_NO_PROJECT_ROOT_HEADER=1
export EXPO_DEVTOOLS_LISTEN_ADDRESS=0.0.0.0

# 使用局域网 IP
REACT_NATIVE_PACKAGER_HOSTNAME=$(ipconfig getifaddr en0 2>/dev/null || echo "192.168.3.246")
export REACT_NATIVE_PACKAGER_HOSTNAME

echo "Starting EvoLoop Mobile..."
echo "Metro will be available at: http://$REACT_NATIVE_PACKAGER_HOSTNAME:8081"
echo "Environment: EXPO_NO_PROJECT_ROOT_HEADER=1"
echo ""

cd "$(dirname "$0")"
npx expo start --lan "$@"
