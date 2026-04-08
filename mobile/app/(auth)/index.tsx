// 认证入口 - 自动跳转到首页（支持游客模式）

import { useEffect, useState } from 'react';
import { router, useRootNavigationState } from 'expo-router';
import { useAuthStore } from '@/stores/authStore';
import { View } from 'react-native';

export default function AuthIndex() {
  const { isLoggedIn } = useAuthStore();
  const rootNavigationState = useRootNavigationState();
  const [hasNavigated, setHasNavigated] = useState(false);

  useEffect(() => {
    // 等待导航挂载完成
    if (!rootNavigationState?.key || hasNavigated) {
      return;
    }

    // 无论是否登录，都直接进入首页（聊天页面）
    // 首页支持游客模式
    const timer = setTimeout(() => {
      setHasNavigated(true);
      router.replace('/(main)');
    }, 0);

    return () => clearTimeout(timer);
  }, [rootNavigationState?.key, hasNavigated, isLoggedIn]);

  // 不渲染任何内容，立即跳转
  return <View style={{ flex: 1, backgroundColor: '#fff' }} />;
}
