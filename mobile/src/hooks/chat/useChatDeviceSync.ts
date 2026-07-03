// 设备-对话同步 Hook
// 提取自 ChatScreen，处理设备切换、对话恢复、AsyncStorage 持久化

import { useState, useCallback, useEffect, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useConversationStore } from '@/stores/conversationStore';

interface UseChatDeviceSyncOptions {
  isLoggedIn: boolean;
  selectedDeviceKey?: string;
  projectId?: number; // 增加项目 ID 联动
  setGlobalMode: (enabled: boolean) => void;
  loadConversations: (projectId?: number, refresh?: boolean, deviceKey?: string) => Promise<void>;
}

export function useChatDeviceSync({
  isLoggedIn,
  selectedDeviceKey,
  projectId,
  setGlobalMode,
  loadConversations,
}: UseChatDeviceSyncOptions) {
  const [deviceConversationMap, setDeviceConversationMap] = useState<Record<string, string>>({});
  const saveDeviceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastProcessedDeviceRef = useRef<string | undefined>(undefined);
  const setCurrentConversation = useConversationStore((state) => state.setCurrentConversation);
  const setActiveDeviceKey = useConversationStore((state) => state.setActiveDeviceKey);

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

  // 设备或项目变化时：刷新对话列表 → 恢复该设备的最近对话或加载最新一个
  useEffect(() => {
    // 如果登录状态或设备 Key 没变，且不是因为项目切换触发，则不重复执行核心同步
    if (!isLoggedIn || !selectedDeviceKey) {
      if (!selectedDeviceKey) {
        lastProcessedDeviceRef.current = undefined;
        // 清除统一设备来源
        setActiveDeviceKey(undefined);
      }
      return;
    }

    const run = async () => {
      // 统一设备来源：立即把当前选中设备同步为 activeDeviceKey
      setActiveDeviceKey(selectedDeviceKey);

      lastProcessedDeviceRef.current = selectedDeviceKey;
      
      // 立即重置当前会话，避免加载过程中看到上一个项目/设备的消息
      setCurrentConversation(null);
      
      // 加载该设备在当前项目（如果有的话）下的会话列表
      await loadConversations(projectId || 0, true, selectedDeviceKey);

      const { conversations: latestConversations } = useConversationStore.getState();
      
      // 优先级 1：从本地 Map 恢复上次在该设备看过的会话
      let targetConversationId = deviceConversationMap[selectedDeviceKey];
      
      // 验证恢复的会话是否还在列表中（可能被删了）
      if (targetConversationId && !latestConversations.some(c => c.id === targetConversationId)) {
        targetConversationId = undefined;
        saveDeviceConversation(selectedDeviceKey, null);
      }

      // 优先级 2：如果本地没记，或者记录的已失效，则自动取列表中的第一个（最新一个）
      if (!targetConversationId && latestConversations.length > 0) {
        targetConversationId = latestConversations[0].id;
        // 自动保存这个“最新”作为该设备的当前会话
        saveDeviceConversation(selectedDeviceKey, targetConversationId);
      }

      // 执行切换
      setCurrentConversation(targetConversationId || null);
    };

    run();
    // 依赖项中移除 deviceConversationMap，避免保存操作触发回流；增加 projectId 确保切换项目时也同步
  }, [isLoggedIn, selectedDeviceKey, projectId, setCurrentConversation, setGlobalMode, loadConversations, setActiveDeviceKey]);

  return { deviceConversationMap, saveDeviceConversation };
}
