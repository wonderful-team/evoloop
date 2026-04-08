// 根布局

import { useEffect, useState } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { PaperProvider } from 'react-native-paper';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { ThemeProvider, useTheme } from '@/components/ui/ThemeProvider';
import { LoadingProvider } from '@/components/ui/LoadingProvider';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { initAuthStore } from '@/stores/authStore';
import '@/locales';

// 带主题的导航组件
function ThemedContent() {
  const { isDark, theme } = useTheme();

  return (
    <PaperProvider theme={theme}>
      <Stack
        screenOptions={{
          headerShown: false,
          animation: 'slide_from_right',
        }}
      >
        {/* 主应用 - 允许游客访问首页 */}
        <Stack.Screen name="(main)" options={{ animation: 'fade' }} />
        {/* 认证相关 */}
        <Stack.Screen name="(auth)" options={{ animation: 'fade' }} />
        {/* 订阅 */}
        <Stack.Screen name="(subscription)" />
        {/* 设置 */}
        <Stack.Screen name="settings" />
        {/* 帮助 */}
        <Stack.Screen name="help" options={{ title: '帮助与反馈' }} />
        {/* 404 */}
        <Stack.Screen name="+not-found" options={{ title: '页面未找到' }} />
      </Stack>
      <StatusBar style={isDark ? 'light' : 'dark'} />
    </PaperProvider>
  );
}

// 根组件
export default function RootLayout() {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // 应用启动初始化
    console.log('EvoLoop Mobile App Started');
    
    // 初始化认证状态
    initAuthStore().then(() => {
      setIsReady(true);
    });
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <LoadingProvider>
            <ErrorBoundary>
              <ThemedContent />
            </ErrorBoundary>
          </LoadingProvider>
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
