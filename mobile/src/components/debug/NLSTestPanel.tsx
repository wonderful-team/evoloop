// NLS 语音识别测试面板

import React, { useState, useCallback } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { Text, Button, Card, Divider, TextInput } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';
import { useNLS } from '@/hooks/useNLS';
import { nlsTokenManager } from '@/services/nls';
import {GATEWAY_BASE_URL, NLS_CONFIG} from "@/constants/config";

interface LogEntry {
  id: string;
  timestamp: string;
  level: 'info' | 'success' | 'warn' | 'error';
  message: string;
}

export function NLSTestPanel() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [testText, setTestText] = useState('');
  const [tokenInfo, setTokenInfo] = useState<string>('');

  const addLog = useCallback((level: LogEntry['level'], message: string) => {
    const entry: LogEntry = {
      id: Date.now().toString(),
      timestamp: new Date().toLocaleTimeString(),
      level,
      message,
    };
    setLogs(prev => [entry, ...prev].slice(0, 100)); // 保留最近 100 条
  }, []);

  // NLS Hook
  const {
    state,
    isRecording,
    currentText,
    volume,
    start,
    stop,
  } = useNLS({
    onResult: (text, isFinal) => {
      addLog(isFinal ? 'success' : 'info', `${isFinal ? '🎤' : '📝'} ${text}`);
    },
    onError: (error) => {
      addLog('error', `❌ ${t('debug.errorPrefix')} ${error.message}`);
    },
    onStateChange: (newState) => {
      addLog('info', `📊 ${t('debug.stateChange', { state: newState })}`);
    },
  });

  // 测试 Token 获取
  const testToken = async () => {
    addLog('info', `🔑 ${t('debug.startTestToken')}`);
    try {
      const token = await nlsTokenManager.getValidToken();
      const expireTime = nlsTokenManager.getExpireTime();
      const expireDate = new Date(expireTime).toLocaleString();

      setTokenInfo(`Token: ${token.substring(0, 20)}...\n${t('debug.tokenExpireTime', { expireDate })}`);
      addLog('success', `✅ ${t('debug.tokenSuccess', { expireDate })}`);
    } catch (error: any) {
      addLog('error', `❌ ${t('debug.tokenFailed', { message: error.message })}`);
    }
  };

  // 测试录音权限
  const testPermission = async () => {
    addLog('info', `🔒 ${t('debug.checkMicPermission')}`);
    // 权限检查会在 useNLS 中自动进行
    addLog('info', `✅ ${t('debug.permissionCheckDone')}`);
  };

  // 开始/停止录音
  const toggleRecording = async () => {
    if (isRecording) {
      addLog('info', `⏹️ ${t('debug.stopRecording')}`);
      await stop();
      addLog('success', `✅ ${t('debug.recordingStopped')}`);
    } else {
      addLog('info', `🎙️ ${t('debug.startRecordingLog')}`);
      try {
        await start();
        addLog('success', `✅ ${t('debug.recordingStarted')}`);
      } catch (error: any) {
        addLog('error', `❌ ${t('debug.startFailed', { message: error.message })}`);
      }
    }
  };

  // 清空日志
  const clearLogs = () => {
    setLogs([]);
    addLog('info', `🗑️ ${t('debug.logsCleared')}`);
  };

  const getLevelColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'info': return colors.onSurfaceVariant;
      case 'success': return colors.success || '#00C853';
      case 'warn': return colors.warning || '#FFAB00';
      case 'error': return colors.error;
      default: return colors.onSurfaceVariant;
    }
  };

  return (
    <ScrollView style={[styles.container, { backgroundColor: colors.background }]}>
      {/* 状态卡片 */}
      <Card style={styles.card}>
        <Card.Title
          title={t('debug.nlsRealtimeTitle')}
          subtitle={`${t('debug.currentStatus', { state })}`}
          left={(props) => (
            <MaterialIcons
              {...props}
              name={isRecording ? 'mic' : 'mic-none'}
              size={24}
              color={isRecording ? colors.error : colors.primary}
            />
          )}
        />
        <Card.Content>
          {/* 音量指示器 */}
          <View style={styles.volumeContainer}>
            <Text variant="bodySmall">{t('debug.volume', { volume: Math.round(volume * 100) })}</Text>
            <View style={[styles.volumeBar, { backgroundColor: colors.surfaceVariant }]}>
              <View
                style={[
                  styles.volumeFill,
                  {
                    width: `${volume * 100}%`,
                    backgroundColor: isRecording ? colors.error : colors.primary,
                  },
                ]}
              />
            </View>
          </View>

          {/* 当前识别文本 */}
          <View style={[styles.textContainer, { backgroundColor: colors.surfaceVariant }]}>
            <Text variant="bodyMedium" style={{ color: colors.onSurface }}>
              {currentText || t('debug.waitingForVoice')}
            </Text>
          </View>
        </Card.Content>
        <Card.Actions>
          <Button
            mode={isRecording ? 'contained' : 'outlined'}
            onPress={toggleRecording}
            icon={isRecording ? 'stop' : 'microphone'}
            buttonColor={isRecording ? colors.error : undefined}
            textColor={isRecording ? '#fff' : undefined}
          >
            {isRecording ? t('debug.stop') : t('debug.startRecording')}
          </Button>
        </Card.Actions>
      </Card>

      {/* Token 测试卡片 */}
      <Card style={styles.card}>
        <Card.Title
          title={t('debug.tokenTest')}
          subtitle={t('debug.tokenTestSubtitle')}
          left={(props) => <MaterialIcons {...props} name="vpn-key" size={24} />}
        />
        <Card.Content>
          {tokenInfo ? (
            <Text variant="bodySmall" style={styles.tokenText}>
              {tokenInfo}
            </Text>
          ) : (
            <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
              {t('debug.clickToTestToken')}
            </Text>
          )}
        </Card.Content>
        <Card.Actions>
          <Button onPress={testToken} icon="refresh">
            {t('debug.getToken')}
          </Button>
          <Button onPress={testPermission} icon="shield-check">
            {t('debug.checkPermission')}
          </Button>
        </Card.Actions>
      </Card>

      {/* 环境配置卡片 */}
      <Card style={styles.card}>
        <Card.Title
          title={t('debug.envConfig')}
          subtitle={t('debug.envConfigSubtitle')}
          left={(props) => <MaterialIcons {...props} name="settings" size={24} />}
        />
        <Card.Content>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            AppKey: {NLS_CONFIG.appKey ? `✅ ${t('debug.configured')}` : `❌ ${t('debug.notConfigured')}`}
            {'\n'}
            Gateway: {GATEWAY_BASE_URL || t('debug.useDefaultAddress')}
            {'\n'}
            {t('debug.devMode')}: {__DEV__ ? t('debug.yes') : t('debug.no')}
          </Text>
        </Card.Content>
      </Card>

      {/* 日志面板 */}
      <Card style={styles.card}>
        <Card.Title
          title={t('debug.runtimeLogs')}
          subtitle={t('debug.logCount', { count: logs.length })}
          left={(props) => <MaterialIcons {...props} name="list" size={24} />}
          right={(props) => (
            <TouchableOpacity onPress={clearLogs} {...props}>
              <MaterialIcons name="delete" size={20} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          )}
        />
        <Card.Content>
          <ScrollView style={styles.logContainer} nestedScrollEnabled>
            {logs.map((log) => (
              <View key={log.id} style={styles.logEntry}>
                <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant, fontSize: 10 }}>
                  {log.timestamp}
                </Text>
                <Text
                  variant="bodySmall"
                  style={{ color: getLevelColor(log.level), marginTop: 2 }}
                >
                  {log.message}
                </Text>
              </View>
            ))}
            {logs.length === 0 && (
              <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant, textAlign: 'center' }}>
                {t('debug.noLogs')}
              </Text>
            )}
          </ScrollView>
        </Card.Content>
      </Card>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
  },
  card: {
    marginBottom: 16,
  },
  volumeContainer: {
    marginBottom: 16,
  },
  volumeBar: {
    height: 8,
    borderRadius: 4,
    marginTop: 8,
    overflow: 'hidden',
  },
  volumeFill: {
    height: '100%',
    borderRadius: 4,
  },
  textContainer: {
    padding: 12,
    borderRadius: 8,
    minHeight: 60,
  },
  tokenText: {
    fontFamily: 'monospace',
    fontSize: 12,
  },
  logContainer: {
    maxHeight: 200,
    backgroundColor: 'rgba(0,0,0,0.02)',
    borderRadius: 8,
    padding: 8,
  },
  logEntry: {
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.05)',
  },
});

export default NLSTestPanel;
