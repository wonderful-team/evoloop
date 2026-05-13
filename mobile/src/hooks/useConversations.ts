// 会话/消息查询 Hook
// 用于 Mobile 端查询 MC 存储的对话历史

import { useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import * as conversationApi from '@/services/api/conversations';
import { Conversation, ConversationHistoryResponse } from '@/types/conversation';
import { ChatMessage } from '@/types/chat';
import { isAuthError } from '@/utils/error';

interface UseConversationsOptions {
  projectId?: number;
  deviceKey?: string;
  pageSize?: number;
}

export function useConversations(options: UseConversationsOptions = {}) {
  const { projectId, deviceKey, pageSize = 20 } = options;
  const toast = useToast();
  const { t } = useTranslation();
  
  // 会话列表状态
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [hasMoreConversations, setHasMoreConversations] = useState(true);
  const conversationsPageRef = useRef(1);
  // 当前生效的筛选条件（用于 loadMore 时保持一致）
  const activeProjectIdRef = useRef<number | undefined>(projectId);
  const activeDeviceKeyRef = useRef<string | undefined>(deviceKey);
  
  // 消息状态
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [hasMoreMessages, setHasMoreMessages] = useState(true);
  const beforeMessageIdRef = useRef<string | undefined>();
  
  // 当前会话
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);

  /**
   * 加载会话列表
   */
  const loadConversations = useCallback(async (refresh = false, overrideDeviceKey?: string, overrideProjectId?: number) => {
    if (isLoadingConversations) return;

    // 确定本次使用的筛选条件
    const resolvedProjectId = overrideProjectId !== undefined ? overrideProjectId : activeProjectIdRef.current;
    const resolvedDeviceKey = overrideDeviceKey !== undefined ? overrideDeviceKey : activeDeviceKeyRef.current;

    // 筛选条件发生变化时强制 refresh
    const filterChanged =
      resolvedProjectId !== activeProjectIdRef.current ||
      resolvedDeviceKey !== activeDeviceKeyRef.current;
    const shouldRefresh = refresh || filterChanged;

    if (shouldRefresh) {
      activeProjectIdRef.current = resolvedProjectId;
      activeDeviceKeyRef.current = resolvedDeviceKey;
      conversationsPageRef.current = 1;
    }
    
    setIsLoadingConversations(true);
    
    try {
      const page = shouldRefresh ? 1 : conversationsPageRef.current;
      const response = await conversationApi.getConversations(resolvedProjectId, page, pageSize, resolvedDeviceKey);
      
      const newConversations = response.conversations || [];
      
      setConversations(prev => 
        shouldRefresh ? newConversations : [...prev, ...newConversations]
      );
      setHasMoreConversations(newConversations.length === pageSize);
      conversationsPageRef.current = page + 1;
    } catch (error: any) {
      if (!isAuthError(error)) {
        console.error('加载会话列表失败:', error);
        toast.show(t('chat.toast.loadConversationsFailed'), 'error');
      }
    } finally {
      setIsLoadingConversations(false);
    }
  }, [isLoadingConversations, pageSize, toast]);

  /**
   * 加载更多会话
   */
  // 加载更多会话——自动氺用已记录的筛选条件
  const loadMoreConversations = useCallback(async () => {
    if (!hasMoreConversations || isLoadingConversations) return;
    await loadConversations(false);
  }, [hasMoreConversations, isLoadingConversations, loadConversations]);

  const getConversationDetail = useCallback(async (conversationId: string) => {
    try {
      const conversation = await conversationApi.getConversation(conversationId);
      setCurrentConversation(conversation);
      
      // 标记为已读，消除跨端未读红点和后台提醒
      conversationApi.markAsRead(conversationId).catch(err => {
        console.log('[useConversations] markAsRead fail:', err);
      });
      
      return conversation;
    } catch (error: any) {
      if (!isAuthError(error)) {
        console.error('获取会话详情失败:', error);
        toast.show(t('chat.toast.getConversationDetailFailed'), 'error');
      }
      return null;
    }
  }, [toast]);

  /**
   * 加载消息历史
   */
  const loadMessages = useCallback(async (conversationId: string, refresh = false) => {
    if (isLoadingMessages) return;
    
    setIsLoadingMessages(true);
    
    try {
      const beforeMessageId = refresh ? undefined : beforeMessageIdRef.current;
      const response = await conversationApi.getConversationHistory(
        conversationId,
        beforeMessageId,
        pageSize
      );
      
      const newMessages = response.messages || [];
      
      setMessages(prev => 
        refresh ? newMessages : [...newMessages, ...prev] // 旧消息在前
      );
      
      setHasMoreMessages(newMessages.length === pageSize);
      
      // 更新分页标记
      if (newMessages.length > 0) {
        beforeMessageIdRef.current = newMessages[0].id;
      }
    } catch (error: any) {
      if (!isAuthError(error)) {
        console.error('加载消息失败:', error);
        toast.show(t('chat.toast.loadMessagesFailed'), 'error');
      }
    } finally {
      setIsLoadingMessages(false);
    }
  }, [pageSize, toast]);

  /**
   * 加载更多历史消息
   */
  const loadMoreMessages = useCallback(async (conversationId: string) => {
    if (!hasMoreMessages || isLoadingMessages) return;
    await loadMessages(conversationId, false);
  }, [hasMoreMessages, isLoadingMessages, loadMessages]);

  /**
   * 删除会话
   */
  const deleteConversation = useCallback(async (conversationId: string) => {
    try {
      await conversationApi.deleteConversation(conversationId);
      
      // 从列表中移除
      setConversations(prev => prev.filter(c => c.id !== conversationId));
      
      // 如果删除的是当前会话，清空
      if (currentConversation?.id === conversationId) {
        setCurrentConversation(null);
        setMessages([]);
      }
      
      toast.show(t('chat.toast.deleteConversationSuccess'), 'success');
    } catch (error: any) {
      if (!isAuthError(error)) {
        console.error('删除会话失败:', error);
        toast.show(t('chat.toast.deleteConversationFailed'), 'error');
      }
    }
  }, [currentConversation, toast]);

  /**
   * 创建新会话
   */
  const createConversation = useCallback(async (initialMessage?: string) => {
    try {
      const response = await conversationApi.createConversation({
        project_id: projectId,
        initial_message: initialMessage,
      });
      
      // 刷新列表
      await loadConversations(true);
      
      toast.show(t('chat.toast.createConversationSuccess'), 'success');
      return response.conversation_id;
    } catch (error: any) {
      if (!isAuthError(error)) {
        console.error('创建会话失败:', error);
        toast.show(t('chat.toast.createConversationFailed'), 'error');
      }
      return null;
    }
  }, [projectId, loadConversations, toast]);

  /**
   * 发送消息 (HTTP 方式)
   */
  const sendMessage = useCallback(async (
    conversationId: string,
    content: string,
    options?: {
      model?: string;
      references?: any[];
    }
  ) => {
    try {
      const response = await conversationApi.sendMessage(
        conversationId,
        content,
        undefined, // attachments
        options
      );
      
      return response.message_id;
    } catch (error: any) {
      if (!isAuthError(error)) {
        console.error('发送消息失败:', error);
        toast.show(t('chat.toast.sendMessageFailed'), 'error');
      }
      return null;
    }
  }, [toast]);

  /**
   * 停止 Agent
   */
  const stopAgent = useCallback(async (conversationId: string) => {
    try {
      await conversationApi.stopAgent(conversationId, activeDeviceKeyRef.current);
      toast.show(t('chat.toast.stopSuccess'), 'success');
    } catch (error: any) {
      if (!isAuthError(error)) {
        console.error('停止失败:', error);
        toast.show(t('chat.toast.stopFailed'), 'error');
      }
    }
  }, [toast]);

  /**
   * 刷新当前会话
   */
  const refreshCurrent = useCallback(async () => {
    if (currentConversation?.id) {
      await getConversationDetail(currentConversation.id);
      await loadMessages(currentConversation.id, true);
    }
  }, [currentConversation, getConversationDetail, loadMessages]);

  /**
   * 清空状态
   */
  const reset = useCallback(() => {
    setConversations([]);
    setMessages([]);
    setCurrentConversation(null);
    setHasMoreConversations(true);
    setHasMoreMessages(true);
    conversationsPageRef.current = 1;
    beforeMessageIdRef.current = undefined;
  }, []);

  return {
    // 会话列表
    conversations,
    isLoadingConversations,
    hasMoreConversations,
    loadConversations,
    loadMoreConversations,
    
    // 当前会话
    currentConversation,
    setCurrentConversation,
    getConversationDetail,
    createConversation,
    deleteConversation,
    
    // 消息
    messages,
    isLoadingMessages,
    hasMoreMessages,
    loadMessages,
    loadMoreMessages,
    sendMessage,
    
    // 控制
    stopAgent,
    refreshCurrent,
    reset,
  };
}

export default useConversations;
