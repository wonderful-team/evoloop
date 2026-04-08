// 会话/消息查询 Hook
// 用于 Mobile 端查询 MC 存储的对话历史

import { useState, useCallback, useRef } from 'react';
import { useToast } from '@/contexts/ToastContext';
import * as conversationApi from '@/services/api/conversations';
import { Conversation, ConversationHistoryResponse } from '@/types/conversation';
import { ChatMessage } from '@/types/chat';

interface UseConversationsOptions {
  projectId?: number;
  pageSize?: number;
}

export function useConversations(options: UseConversationsOptions = {}) {
  const { projectId, pageSize = 20 } = options;
  const toast = useToast();
  
  // 会话列表状态
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [hasMoreConversations, setHasMoreConversations] = useState(true);
  const conversationsPageRef = useRef(1);
  
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
  const loadConversations = useCallback(async (refresh = false) => {
    if (isLoadingConversations) return;
    
    setIsLoadingConversations(true);
    
    try {
      const page = refresh ? 1 : conversationsPageRef.current;
      const response = await conversationApi.getConversations(projectId, page, pageSize);
      
      const newConversations = response.list || [];
      
      setConversations(prev => 
        refresh ? newConversations : [...prev, ...newConversations]
      );
      setHasMoreConversations(newConversations.length === pageSize);
      conversationsPageRef.current = page + 1;
    } catch (error: any) {
      console.error('加载会话列表失败:', error);
      toast.show('加载会话列表失败', 'error');
    } finally {
      setIsLoadingConversations(false);
    }
  }, [projectId, pageSize, toast]);

  /**
   * 加载更多会话
   */
  const loadMoreConversations = useCallback(async () => {
    if (!hasMoreConversations || isLoadingConversations) return;
    await loadConversations(false);
  }, [hasMoreConversations, isLoadingConversations, loadConversations]);

  /**
   * 获取会话详情
   */
  const getConversationDetail = useCallback(async (conversationId: string) => {
    try {
      const conversation = await conversationApi.getConversation(conversationId);
      setCurrentConversation(conversation);
      return conversation;
    } catch (error: any) {
      console.error('获取会话详情失败:', error);
      toast.show('获取会话详情失败', 'error');
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
      console.error('加载消息失败:', error);
      toast.show('加载消息失败', 'error');
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
      
      toast.show('会话已删除', 'success');
    } catch (error: any) {
      console.error('删除会话失败:', error);
      toast.show('删除会话失败', 'error');
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
      
      toast.show('会话创建成功', 'success');
      return response.conversation_id;
    } catch (error: any) {
      console.error('创建会话失败:', error);
      toast.show('创建会话失败', 'error');
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
      console.error('发送消息失败:', error);
      toast.show('发送消息失败', 'error');
      return null;
    }
  }, [toast]);

  /**
   * 停止 Agent
   */
  const stopAgent = useCallback(async (conversationId: string) => {
    try {
      await conversationApi.stopAgent(conversationId);
      toast.show('已停止生成', 'success');
    } catch (error: any) {
      console.error('停止失败:', error);
      toast.show('停止失败', 'error');
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
