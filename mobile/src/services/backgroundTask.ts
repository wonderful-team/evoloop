// 后台轮询服务 - 定期检查新消息
// 频率：正常后台 2分钟，息屏/APP关闭 5分钟

import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import BackgroundFetch from 'react-native-background-fetch';
import { api } from '@/services/api/client';

const LAST_CHECK_TIME_KEY = '@evoloop_last_check_time';
const LAST_MESSAGE_ID_KEY = '@evoloop_last_message_id';
const CHECK_INTERVAL_NORMAL = 2 * 60 * 1000; // 2分钟
const CHECK_INTERVAL_BACKGROUND = 5 * 60 * 1000; // 5分钟

// 检查新消息
async function checkNewMessages(): Promise<boolean> {
  try {
    const token = await AsyncStorage.getItem('token');
    if (!token) {
      console.log('[BackgroundTask] No token, skipping check');
      return false;
    }

    // 获取上次检查的消息ID
    const lastMessageId = await AsyncStorage.getItem(LAST_MESSAGE_ID_KEY);

    // 获取最新的对话列表
    let data: any;
    try {
      data = await api.get('/member/evolooplink/api/conversation/list?page=1&page_size=1');
    } catch (error) {
      console.log('[BackgroundTask] Failed to fetch conversations:', error);
      return false;
    }
    if (data.code !== 0 || !data.data?.list?.length) {
      return false;
    }

    const latestConversation = data.data.list[0];
    const conversationId = latestConversation.conversation_id;

    // 获取该对话的最新消息
    let messagesData: any;
    try {
      messagesData = await api.get(`/member/evolooplink/api/conversation/messages?conversation_id=${conversationId}&limit=1`);
    } catch (error) {
      return false;
    }
    if (messagesData.code !== 0 || !messagesData.data?.length) {
      return false;
    }

    const latestMessage = messagesData.data[0];
    const currentMessageId = String(latestMessage.message_id || latestMessage.id);

    // 检查是否是新消息
    if (lastMessageId && currentMessageId !== lastMessageId) {
      // 有新消息
      if (latestMessage.role === 'assistant') {
        // 显示本地通知
        await showNotification(
          'EvoLoop AI',
          latestMessage.content?.substring(0, 100) || '收到新消息'
        );
        return true;
      }
    }

    // 更新最后检查的消息ID
    await AsyncStorage.setItem(LAST_MESSAGE_ID_KEY, currentMessageId);
    return false;

  } catch (error) {
    console.error('[BackgroundTask] Check failed:', error);
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
        name: '新消息通知',
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

// 设置最后检查的消息ID（发送消息后调用）
export async function setLastMessageId(messageId: string): Promise<void> {
  await AsyncStorage.setItem(LAST_MESSAGE_ID_KEY, messageId);
}
