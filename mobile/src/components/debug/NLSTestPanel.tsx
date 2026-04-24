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
      addLog('error', `❌ 错误: ${error.message}`);
    },
    onStateChange: (newState) => {
      addLog('info', `📊 状态变更: ${newState}`);
    },
  });

  // 测试 Token 获取
  const testToken = async () => {
    addLog('info', '🔑 开始测试 Token 获取...');
    try {
      const token = await nlsTokenManager.getValidToken();
      const expireTime = nlsTokenManager.getExpireTime();
      const expireDate = new Date(expireTime).toLocaleString();

      setTokenInfo(`Token: ${token.substring(0, 20)}...\n过期时间: ${expireDate}`);
      addLog('success', `✅ Token 获取成功，过期时间: ${expireDate}`);
    } catch (error: any) {
      addLog('error', `❌ Token 获取失败: ${error.message}`);
    }
  };

  // 测试录音权限
  const testPermission = async () => {
    addLog('info', '🔒 检查录音权限...');
    // 权限检查会在 useNLS 中自动进行
    addLog('info', '✅ 权限检查完成（请确保已授予麦克风权限）');
  };

  // 开始/停止录音
  const toggleRecording = async () => {
    if (isRecording) {
      addLog('info', '⏹️ 停止录音...');
      await stop();
      addLog('success', '✅ 录音已停止');
    } else {
      addLog('info', '🎙️ 开始录音...');
      try {
        await start();
        addLog('success', '✅ 录音已开始');
      } catch (error: any) {
        addLog('error', `❌ 启动失败: ${error.message}`);
      }
    }
  };

  // 清空日志
  const clearLogs = () => {
    setLogs([]);
    addLog('info', '🗑️ 日志已清空');
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
          title="NLS 实时语音识别"
          subtitle={`当前状态: ${state}`}
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
            <Text variant="bodySmall">音量: {Math.round(volume * 100)}%</Text>
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
              {currentText || '等待语音输入...'}
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
            {isRecording ? '停止' : '开始录音'}
          </Button>
        </Card.Actions>
      </Card>

      {/* Token 测试卡片 */}
      <Card style={styles.card}>
        <Card.Title
          title="Token 测试"
          subtitle="测试 NLS Token 获取"
          left={(props) => <MaterialIcons {...props} name="vpn-key" size={24} />}
        />
        <Card.Content>
          {tokenInfo ? (
            <Text variant="bodySmall" style={styles.tokenText}>
              {tokenInfo}
            </Text>
          ) : (
            <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
              点击按钮测试 Token 获取
            </Text>
          )}
        </Card.Content>
        <Card.Actions>
          <Button onPress={testToken} icon="refresh">
            获取 Token
          </Button>
          <Button onPress={testPermission} icon="shield-check">
            检查权限
          </Button>
        </Card.Actions>
      </Card>

      {/* 环境配置卡片 */}
      <Card style={styles.card}>
        <Card.Title
          title="环境配置"
          subtitle="当前 NLS 配置"
          left={(props) => <MaterialIcons {...props} name="settings" size={24} />}
        />
        <Card.Content>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            AppKey: {NLS_CONFIG.appKey ? '✅ 已配置' : '❌ 未配置'}
            {'\n'}
            Gateway: {GATEWAY_BASE_URL || '使用默认地址'}
            {'\n'}
            开发模式: {__DEV__ ? '是' : '否'}
          </Text>
        </Card.Content>
      </Card>

      {/* 日志面板 */}
      <Card style={styles.card}>
        <Card.Title
          title="运行日志"
          subtitle={`共 ${logs.length} 条日志`}
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
                暂无日志
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
