// 设备-对话同步 Hook
// 提取自 ChatScreen，处理设备切换、对话恢复、AsyncStorage 持久化

import { useState, useCallback, useEffect, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useConversationStore } from '@/stores/conversationStore';

interface UseChatDeviceSyncOptions {
  isLoggedIn: boolean;
  selectedDeviceKey?: string;
  setGlobalMode: (enabled: boolean) => void;
  loadConversations: (projectId?: number, refresh?: boolean, deviceKey?: string) => Promise<void>;
}

export function useChatDeviceSync({
  isLoggedIn,
  selectedDeviceKey,
  setGlobalMode,
  loadConversations,
}: UseChatDeviceSyncOptions) {
  const [deviceConversationMap, setDeviceConversationMap] = useState<Record<string, string>>({});
  const saveDeviceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const setCurrentConversation = useConversationStore((state) => state.setCurrentConversation);

  // 从 AsyncStorage 加载设备-对话映射
  useEffect(() => {
    AsyncStorage.getItem('device_conversation_map')
      .then((saved) => {
        if (saved) {
          try {
            const map = JSON.parse(saved);
            setDeviceConversationMap(map);
          } catch {
            // 解析失败静默处理
          }
        }
      })
      .catch(() => {});
  }, []);

  // 保存设备-对话映射（内存立即更新，AsyncStorage debounce 500ms）
  const saveDeviceConversation = useCallback((deviceKey: string, conversationId: string | null) => {
    setDeviceConversationMap((prev) => {
      const map = { ...prev };
      if (conversationId) {
        map[deviceKey] = conversationId;
      } else {
        delete map[deviceKey];
      }
      if (saveDeviceTimerRef.current) {
        clearTimeout(saveDeviceTimerRef.current);
      }
      saveDeviceTimerRef.current = setTimeout(() => {
        AsyncStorage.setItem('device_conversation_map', JSON.stringify(map)).catch(() => {});
      }, 500);
      return map;
    });
  }, []);

  // 设备变化时：进入全局模式 → 刷新对话列表 → 恢复该设备的最近对话
  useEffect(() => {
    if (!isLoggedIn || !selectedDeviceKey) return;

    const run = async () => {
      setGlobalMode(true);
      await loadConversations(undefined, true, selectedDeviceKey);

      const { conversations: latestConversations, currentConversationId: latestCurrentId } = useConversationStore.getState();
      const conversationId = deviceConversationMap[selectedDeviceKey];
      if (conversationId) {
        const exists = latestConversations.some((c) => c.id === conversationId);
        if (exists && latestCurrentId !== conversationId) {
          setCurrentConversation(conversationId);
        } else if (!exists) {
          saveDeviceConversation(selectedDeviceKey, null);
          if (latestCurrentId !== null) {
            setCurrentConversation(null);
          }
        }
      } else {
        if (latestCurrentId !== null) {
          setCurrentConversation(null);
        }
      }
    };

    run();
  }, [isLoggedIn, selectedDeviceKey, deviceConversationMap, setCurrentConversation, saveDeviceConversation, setGlobalMode, loadConversations]);

  return { deviceConversationMap, saveDeviceConversation };
}
