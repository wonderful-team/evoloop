// 首页 - 语音对话主界面（支持游客模式）

import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  Modal,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { MaterialIcons } from '@expo/vector-icons';
import { Text, Snackbar, Menu } from 'react-native-paper';
import {
  MessageList,
  VoiceInput,
  InputMode,
} from '@/components/voice';
import { HITLBanner } from '@/components/hitl';
import { useVoice } from '@/hooks/useVoice';
import { useConversationStore } from '@/stores/conversationStore';
import { useTheme } from '@/theme';
import { useAuthStore } from '@/stores/authStore';
import { HumanRequest } from '@/types/hitl';
import { Project } from '@/types';
import type { ChatAttachment } from '@/services/api/upload';
import AsyncStorage from '@react-native-async-storage/async-storage';

// 游客默认项目
const GUEST_PROJECTS: Project[] = [
  { id: 0, name: '示例项目', rootPath: '/demo', description: '游客体验项目', isActive: true },
];

export default function HomeScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();
  const { isLoggedIn } = useAuthStore();
  
  // 输入模式
  const [inputMode, setInputMode] = useState<InputMode>(InputMode.VOICE);
  
  // UI 状态
  const [showProjectMenu, setShowProjectMenu] = useState(false);
  const [snackbarVisible, setSnackbarVisible] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  
  // 项目状态
  const [projects, setProjects] = useState<Project[]>(GUEST_PROJECTS);
  const [currentProject, setCurrentProject] = useState<Project>(GUEST_PROJECTS[0]);

  // Store
  const {
    messages,
    loadConversations,
    setCurrentConversation,
  } = useConversationStore();

  // 加载项目
  useEffect(() => {
    const loadProjects = async () => {
      if (!isLoggedIn) {
        const saved = await AsyncStorage.getItem('guest_current_project');
        if (saved) setCurrentProject(JSON.parse(saved));
      }
    };
    loadProjects();
  }, [isLoggedIn]);

  // 语音 Hook
  const {
    state,
    isListening,
    isThinking,
    hitlRequest,
    start,
    stop,
    interrupt,
    sendText: sendTextMessage,
    respondToHITL,
    cancelHITL,
  } = useVoice({
    onError: (error: Error) => showSnackbar('语音错误: ' + error.message),
  });

  useEffect(() => { loadConversations(undefined, true); }, []);
  useEffect(() => {
    start();
    return () => { stop(); };
  }, []);

  const showSnackbar = (message: string) => {
    setSnackbarMessage(message);
    setSnackbarVisible(true);
  };

  const handleVoiceToggle = useCallback(async () => {
    if (isListening) await stop();
    else await start();
  }, [isListening, start, stop]);

  const handleSendMessage = useCallback((text: string) => {
    sendTextMessage(text);
  }, [sendTextMessage]);

  const handleSwitchProject = useCallback(async (project: Project) => {
    setCurrentProject(project);
    setShowProjectMenu(false);
    if (!isLoggedIn) {
      await AsyncStorage.setItem('guest_current_project', JSON.stringify(project));
    }
    showSnackbar(`已切换到: ${project.name}`);
  }, [isLoggedIn]);

  const handleGoToProfile = useCallback(() => {
    router.push('/(main)/profile');
  }, [router]);

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* ===== 头部 ===== */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            {/* 历史按钮 */}
            <TouchableOpacity style={styles.iconBtn}>
              <MaterialIcons name="history" size={24} color={colors.primary} />
            </TouchableOpacity>
            
            {/* 项目选择器 */}
            <Menu
              visible={showProjectMenu}
              onDismiss={() => setShowProjectMenu(false)}
              anchor={
                <TouchableOpacity 
                  style={styles.projectSelector}
                  onPress={() => setShowProjectMenu(true)}
                >
                  <MaterialIcons name="folder" size={18} color={colors.primary} />
                  <Text 
                    variant="titleMedium" 
                    style={[styles.projectName, { color: colors.onBackground }]}
                    numberOfLines={1}
                  >
                    {currentProject?.name}
                  </Text>
                  <MaterialIcons name="arrow-drop-down" size={20} color={colors.onBackground} />
                </TouchableOpacity>
              }
            >
              {projects.map((p) => (
                <Menu.Item
                  key={p.id}
                  onPress={() => handleSwitchProject(p)}
                  title={p.name}
                  leadingIcon={currentProject?.id === p.id ? 'check' : undefined}
                />
              ))}
            </Menu>
          </View>
          
          {/* 右侧我的按钮 */}
          <TouchableOpacity 
            style={styles.iconBtn}
            onPress={handleGoToProfile}
          >
            <MaterialIcons name="person" size={24} color={colors.primary} />
          </TouchableOpacity>
        </View>

        {/* ===== 游客提示（未登录时显示） ===== */}
        {!isLoggedIn && (
          <TouchableOpacity 
            style={[styles.guestBanner, { backgroundColor: colors.primaryContainer }]}
            onPress={() => router.push('/(auth)/login')}
          >
            <MaterialIcons name="info" size={16} color={colors.primary} />
            <Text variant="bodySmall" style={{ color: colors.primary, marginLeft: 8 }}>
              游客模式 - 点击登录
            </Text>
          </TouchableOpacity>
        )}

        {/* ===== 消息列表（核心区域） ===== */}
        <View style={styles.messagesArea}>
          <MessageList 
            messages={messages}
            onRewind={() => {}}
            onRetry={() => {}}
          />
        </View>

        {/* ===== 底部输入区 ===== */}
        <VoiceInput
          state={state}
          onSendText={handleSendMessage}
          onToggleVoice={handleVoiceToggle}
          disabled={isThinking}
          inputMode={inputMode}
          onToggleMode={() => setInputMode(m => m === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE)}
        />
      </KeyboardAvoidingView>

      {/* ===== Snackbar ===== */}
      <Snackbar
        visible={snackbarVisible}
        onDismiss={() => setSnackbarVisible(false)}
        duration={2000}
      >
        {snackbarMessage}
      </Snackbar>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  // 头部
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingTop: Platform.OS === 'ios' ? 60 : 36,
    paddingBottom: 8,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  iconBtn: {
    padding: 8,
    marginRight: 4,
  },
  projectSelector: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  projectName: {
    fontWeight: '600',
    fontSize: 16,
    maxWidth: 140,
    marginHorizontal: 4,
  },
  deviceBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  // 游客横幅
  guestBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    marginHorizontal: 12,
    marginBottom: 4,
    borderRadius: 6,
  },
  // 消息区域
  messagesArea: {
    flex: 1,
  },
});
