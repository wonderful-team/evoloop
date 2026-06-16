import 'react-native-gesture-handler';
import React, { useEffect, useState } from 'react';
import { LogBox, View, ActivityIndicator, Platform, Image, Text } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { PaperProvider } from 'react-native-paper';
import './src/locales'; // 初始化 i18n

// 注册 Notifee 前台服务（唤醒词后台监听必需，非鸿蒙平台适用）
if (Platform.OS !== 'harmony') {
  try {
    const notifee = require('@notifee/react-native').default;
    notifee.registerForegroundService(() => {
      return new Promise(() => {
        // 保持服务运行，直到调用 notifee.stopForegroundService()
      });
    });
  } catch (e) {
    console.error('[App] Failed to register Notifee foreground service:', e);
  }
}

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

if (Platform.OS === 'harmony') {
  LogBox.ignoreAllLogs(true);
}

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
        if (Platform.OS === 'harmony') {
          const EvoLoopDevice = require('./src/services/device/EvoLoopDevice').default;
          await EvoLoopDevice.requestNotificationPermission();
          const pushToken = await EvoLoopDevice.getPushToken();
          console.log('[App] HarmonyOS Push Token:', pushToken);
        } else {
          try {
            const notifee = require('@notifee/react-native').default;
            await notifee.requestPermission();
          } catch (e) {
            console.error('[App] Failed to request Notifee permission:', e);
          }
        }

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
      <View style={{ flex: 1, backgroundColor: '#FFFFFF', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 80 }}>
        <View style={{ height: 40 }} />
        
        <View style={{ alignItems: 'center' }}>
          <Image
            source={require('./src/assets/images/splash-icon.png')}
            style={{ width: 120, height: 120, resizeMode: 'contain' }}
          />
          <ActivityIndicator size="small" color={lightTheme.colors.primary} style={{ marginTop: 24 }} />
        </View>

        <View style={{ alignItems: 'center' }}>
          <Text style={{ fontSize: 16, color: '#555555', fontWeight: '500', letterSpacing: 1.5 }}>
            拥有属于你的AI数字员工
          </Text>
        </View>
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
