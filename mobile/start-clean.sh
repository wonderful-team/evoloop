#!/bin/bash
# 彻底清除所有缓存并启动

echo "🧹 清理所有缓存..."

# 清理 Expo 缓存
rm -rf .expo
rm -rf node_modules/.cache

# 清理 Metro 缓存
rm -rf $TMPDIR/metro-*
rm -rf $TMPDIR/react-*

# 清理 watchman（如果有）
watchman watch-del-all 2>/dev/null || true

# 创建英文路径软链接
mkdir -p ~/dev
rm -f ~/dev/evoloop-mobile
ln -s "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/mobile" ~/dev/evoloop-mobile

echo "✅ 缓存已清理"
echo ""
echo "🚀 从英文路径启动开发服务器..."

# 使用 Java 17
export JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home
export PATH=$JAVA_HOME/bin:$PATH

# 从英文路径启动
cd ~/dev/evoloop-mobile
npx expo start --host lan
