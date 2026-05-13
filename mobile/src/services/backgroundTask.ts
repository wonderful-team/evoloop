// 后台轮询服务 - 定期检查新消息
// 频率：正常后台 2分钟，息屏/APP关闭 5分钟

import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import BackgroundFetch from 'react-native-background-fetch';
import { api } from '@/services/api/client';

const LAST_CHECK_TIME_KEY = '@evoloop_last_check_time';
const CHECK_INTERVAL_NORMAL = 2 * 60 * 1000; // 2分钟
const CHECK_INTERVAL_BACKGROUND = 5 * 60 * 1000; // 5分钟

import { syncMessages } from '@/services/api/conversations';
import i18n from '@/locales';
import { isAuthError } from '@/utils/error';

// 检查新消息
async function checkNewMessages(): Promise<boolean> {
  try {
    const token = await AsyncStorage.getItem('token');
    if (!token) {
      console.log('[BackgroundTask] No token, skipping check');
      return false;
    }

    // 获取上次检查的时间 (秒级)
    const lastCheckStr = await AsyncStorage.getItem(LAST_CHECK_TIME_KEY);
    let lastTime = 0;
    if (lastCheckStr) {
      // 存储的是毫秒级，转为秒级
      lastTime = Math.floor(parseInt(lastCheckStr, 10) / 1000);
    } else {
      // 首次运行，默认只查过去 10 分钟
      lastTime = Math.floor(Date.now() / 1000) - 600;
    }

    const { messages, serverTime } = await syncMessages(lastTime);

    if (messages && messages.length > 0) {
      // 由于后端已经过滤了 role = 'assistant' 和 last_read_time，这些都是有效的新消息
      // 为了防骚扰，只弹最新的一条消息内容，提示有 N 条新消息
      const latestMessage = messages[0]; // 后端是按 create_time desc 返回的
      
      let title = 'EvoLoop AI';
      if (messages.length > 1) {
          title = i18n.t('notifications.newMessageCount', { count: messages.length });
      }

      await showNotification(
        title,
        latestMessage.content?.substring(0, 100) || i18n.t('notifications.newMessageBody')
      );
      
      // 获取所有新消息中最大的时间戳
      const maxTime = Math.max(...messages.map((m: any) => m.create_time));
      
      // 更新最后检查时间 (使用消息中的最大时间，或者服务端时间)
      // 使用毫秒级存储以保持一致
      await AsyncStorage.setItem(LAST_CHECK_TIME_KEY, String(maxTime * 1000));
      
      return true;
    }

    // 如果没有新消息，更新检查时间为服务端当前时间 (秒转毫秒)
    await AsyncStorage.setItem(LAST_CHECK_TIME_KEY, String(serverTime * 1000));
    return false;

  } catch (error) {
    if (isAuthError(error)) {
      console.log('[BackgroundTask] Session expired or unauthorized, pausing checks');
    } else {
      console.error('[BackgroundTask] Check failed due to unexpected error:', error);
    }
    return false;
  }
}


// 显示本地通知
async function showNotification(title: string, body: string): Promise<void> {
  try {
    // 使用 @notifee/react-native 显示通知
    const notifee = require('@notifee/react-native').default;

    // 创建频道（Android）
    if (Platform.OS === 'android') {
      await notifee.createChannel({
        id: 'new-message',
        name: i18n.t('notifications.newMessageChannel'),
        importance: 4, // HIGH
        vibration: true,
        vibrationPattern: [300, 500],
      });
    }

    await notifee.displayNotification({
      title,
      body,
      android: {
        channelId: 'new-message',
        pressAction: {
          id: 'open-chat',
        },
        importance: 'high',
      },
      ios: {
        sound: 'default',
      },
    });

    console.log('[BackgroundTask] Notification shown:', title);
  } catch (error) {
    console.error('[BackgroundTask] Failed to show notification:', error);
  }
}

// 后台任务处理器
async function backgroundTaskHandler(taskId: string): Promise<void> {
  console.log('[BackgroundTask] Running task:', taskId);

  try {
    const hasNewMessage = await checkNewMessages();
    console.log('[BackgroundTask] Has new message:', hasNewMessage);

    // 更新最后检查时间
    await AsyncStorage.setItem(LAST_CHECK_TIME_KEY, String(Date.now()));

    // 完成任务
    BackgroundFetch.finish(taskId);
  } catch (error) {
    console.error('[BackgroundTask] Task error:', error);
    BackgroundFetch.finish(taskId);
  }
}

// 配置后台任务
export async function initBackgroundTask(): Promise<void> {
  try {
    // 配置后台获取
    await BackgroundFetch.configure(
      {
        minimumFetchInterval: 2, // iOS: 最小间隔（分钟），实际由系统决定
        stopOnTerminate: false, // APP关闭后继续运行
        startOnBoot: true, // 开机后自动启动
        enableHeadless: true, // 启用 headless 模式
        requiredNetworkType: BackgroundFetch.NETWORK_TYPE_ANY,
      },
      backgroundTaskHandler,
      (error: any) => {
        console.error('[BackgroundTask] Configure failed:', error);
      }
    );

    // 启动后台任务
    await BackgroundFetch.start();
    console.log('[BackgroundTask] Started successfully');

    // 记录启动时间
    await AsyncStorage.setItem(LAST_CHECK_TIME_KEY, String(Date.now()));

  } catch (error) {
    console.error('[BackgroundTask] Init failed:', error);
  }
}

// 停止后台任务
export async function stopBackgroundTask(): Promise<void> {
  try {
    await BackgroundFetch.stop();
    console.log('[BackgroundTask] Stopped');
  } catch (error) {
    console.error('[BackgroundTask] Stop failed:', error);
  }
}

// 手动触发检查（用于前台手动刷新）
export async function manualCheck(): Promise<boolean> {
  return checkNewMessages();
}
