// 首页 - 语音对话主界面（支持游客模式，使用阿里云 NLS）

import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { MaterialIcons } from '@expo/vector-icons';
import {
  Text,
  Snackbar,
  Menu,
} from 'react-native-paper';
import {
  MessageList,
  VoiceInput,
  InputMode,
} from '@/components/voice';
import { HITLBanner } from '@/components/hitl';
import { useVoice } from '@/hooks/useVoice';
import { useNLS } from '@/hooks/useNLS';
import { useConversationStore } from '@/stores/conversationStore';
import { useTheme } from '@/theme';
import { useAuthStore } from '@/stores/authStore';
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

  // ========== NLS 语音识别 ==========
  const {
    state: nlsState,
    isRecording: nlsIsRecording,
    currentText: nlsCurrentText,
    volume: nlsVolume,
    start: startNLS,
    stop: stopNLS,
  } = useNLS({
    onResult: (text, isFinal) => {
      if (isFinal) {
        // 一句话识别完成，发送给后端对话
        sendTextMessage(text);
      }
    },
    onError: (error) => showSnackbar('语音识别错误: ' + error.message),
  });

  // ========== Gateway 对话 ==========
  const {
    state,
    isListening,
    isThinking,
    hitlRequest,
    sendText: sendTextMessage,
    respondToHITL,
    cancelHITL,
  } = useVoice({
    onError: (error) => showSnackbar('对话错误: ' + error.message),
  });

  useEffect(() => { loadConversations(undefined, true); }, []);

  const showSnackbar = (message: string) => {
    setSnackbarMessage(message);
    setSnackbarVisible(true);
  };

  // 语音按钮点击
  const handleVoiceToggle = useCallback(async () => {
    if (nlsIsRecording) {
      await stopNLS();
    } else {
      await startNLS();
    }
  }, [nlsIsRecording, startNLS, stopNLS]);

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

  // 组合状态（NLS + Gateway）
  const combinedState = nlsIsRecording ? nlsState : state;
  const isListeningCombined = nlsIsRecording || isListening;

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

        {/* ===== 实时识别文字（显示在顶部） ===== */}
        {nlsIsRecording && nlsCurrentText && (
          <View style={[styles.recognizingBanner, { backgroundColor: colors.surfaceVariant }]}>
            <MaterialIcons name="mic" size={16} color={colors.primary} />
            <Text variant="bodySmall" style={{ color: colors.onSurface, marginLeft: 8, flex: 1 }}>
              {nlsCurrentText}
            </Text>
            <View style={[styles.volumeIndicator, { width: nlsVolume * 50 }]} />
          </View>
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
          state={combinedState}
          onSendText={handleSendMessage}
          onToggleVoice={handleVoiceToggle}
          disabled={isThinking}
          inputMode={inputMode}
          onToggleMode={() => setInputMode(m => m === InputMode.VOICE ? InputMode.TEXT : InputMode.VOICE)}
          nlsVolume={nlsVolume}
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
    marginLeft: 6,
    marginRight: 2,
    maxWidth: 120,
  },
  // 游客提示
  guestBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    marginHorizontal: 12,
    marginBottom: 8,
    borderRadius: 8,
  },
  // 识别中提示
  recognizingBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginHorizontal: 12,
    marginBottom: 8,
    borderRadius: 8,
  },
  volumeIndicator: {
    height: 4,
    backgroundColor: '#22C55E',
    borderRadius: 2,
    maxWidth: 50,
  },
  // 消息区域
  messagesArea: {
    flex: 1,
    marginHorizontal: 12,
  },
});
