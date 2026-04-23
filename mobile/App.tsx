import 'react-native-gesture-handler';
import React, { useEffect, useState } from 'react';
import { LogBox, View, ActivityIndicator } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { PaperProvider } from 'react-native-paper';
import notifee from '@notifee/react-native';
import './src/locales'; // 初始化 i18n
import { ToastProvider } from './src/contexts/ToastContext';
import RootNavigator from './src/navigation';
import { navigationRef } from './src/utils/navigation';
import { lightTheme } from './src/constants/theme';
import { initAuthStore } from './src/stores/authStore';
import { initBackgroundTask } from './src/services/backgroundTask';

// 忽略第三方库的原生模块警告
LogBox.ignoreLogs([
  '`new NativeEventEmitter()` was called with a non-null argument without the required `addListener` method.',
  '`new NativeEventEmitter()` was called with a non-null argument without the required `removeListeners` method.',
]);

function App(): React.JSX.Element {
  const [isReady, setIsReady] = useState(false);

  // 初始化时从存储恢复登录状态
  useEffect(() => {
    const init = async () => {
      console.log('[App] Starting auth initialization...');
      try {
        // 等待更长时间确保 persist 完全恢复
        await new Promise(resolve => setTimeout(resolve, 500));
        await initAuthStore();
        console.log('[App] Auth initialization completed');

        // 初始化通知权限
        console.log('[App] Initializing notifications...');
        await notifee.requestPermission();

        // 初始化后台轮询任务
        console.log('[App] Initializing background task...');
        await initBackgroundTask();
        console.log('[App] Background task initialized');
      } catch (error) {
        console.error('[App] Auth initialization error:', error);
      } finally {
        console.log('[App] Setting isReady to true');
        setIsReady(true);
      }
    };
    init();
  }, []);

  // 等待初始化完成
  if (!isReady) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" color={lightTheme.colors.primary} />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <PaperProvider theme={lightTheme}>
          <ToastProvider>
            <NavigationContainer ref={navigationRef}>
              <RootNavigator />
            </NavigationContainer>
          </ToastProvider>
        </PaperProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

export default App;
