// 根布局

import { useEffect } from 'react';
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

// 初始化认证状态
initAuthStore();

// 导航组件
function Navigation() {
  const { isDark } = useTheme();
  
  return (
    <>
      <Stack
        screenOptions={{
          headerShown: false,
          animation: 'slide_from_right',
        }}
      >
        <Stack.Screen name="(auth)" options={{ animation: 'fade' }} />
        <Stack.Screen name="(main)" options={{ animation: 'fade' }} />
        <Stack.Screen name="(subscription)" />
        <Stack.Screen name="onboarding" options={{ animation: 'fade' }} />
        <Stack.Screen name="settings" />
        <Stack.Screen name="help" options={{ title: '帮助与反馈' }} />
        <Stack.Screen name="+not-found" options={{ title: '页面未找到' }} />
      </Stack>
      <StatusBar style={isDark ? 'light' : 'dark'} />
    </>
  );
}

// 根组件
export default function RootLayout() {
  useEffect(() => {
    // 应用启动初始化
    console.log('EvoLoop Mobile App Started');
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <PaperProvider>
            <LoadingProvider>
              <ErrorBoundary>
                <Navigation />
              </ErrorBoundary>
            </LoadingProvider>
          </PaperProvider>
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
