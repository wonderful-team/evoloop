// 语音设置页面

import React, { useState, useEffect } from 'react';
import { View, StyleSheet, ScrollView } from 'react-native';
import { List, Switch, Divider, Text, Button, Slider } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
import { Header } from '@/components/common/Header';
import { AudioRecorder } from '@/services/voice/AudioRecorder';
import AsyncStorage from '@react-native-async-storage/async-storage';

interface VoiceSettings {
  autoStart: boolean;
  continuousListening: boolean;
  wakeWordEnabled: boolean;
  vadThreshold: number;
  silenceTimeout: number;
  language: string;
}

const DEFAULT_SETTINGS: VoiceSettings = {
  autoStart: false,
  continuousListening: true,
  wakeWordEnabled: false,
  vadThreshold: 0.15,
  silenceTimeout: 1500,
  language: 'zh-CN',
};

const LANGUAGE_OPTIONS = [
  { value: 'zh-CN', label: '中文（普通话）' },
  { value: 'en-US', label: 'English (US)' },
  { value: 'zh-HK', label: '中文（粤语）' },
  { value: 'ja-JP', label: '日本語' },
];

export default function VoiceSettingsScreen() {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const colors = theme.colors;
  const [settings, setSettings] = useState<VoiceSettings>(DEFAULT_SETTINGS);
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [showLanguageDialog, setShowLanguageDialog] = useState(false);

  // 加载设置
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const savedSettings = await AsyncStorage.getItem('voice_settings');
        if (savedSettings) {
          setSettings({ ...DEFAULT_SETTINGS, ...JSON.parse(savedSettings) });
        }
      } catch (e) {
        console.error('Failed to parse voice settings:', e);
      }
    };
    loadSettings();
  }, []);

  // 检查麦克风权限
  useEffect(() => {
    AudioRecorder.checkPermissions().then(setHasPermission);
  }, []);

  // 保存设置
  const saveSettings = async (newSettings: Partial<VoiceSettings>) => {
    const updated = { ...settings, ...newSettings };
    setSettings(updated);
    await AsyncStorage.setItem('voice_settings', JSON.stringify(updated));
  };

  // 请求麦克风权限
  const requestPermission = async () => {
    const granted = await AudioRecorder.requestPermissions();
    setHasPermission(granted);
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <Header title="语音设置" showBack />
      <ScrollView>
        {/* 权限状态 */}
      <View style={styles.permissionCard}>
        <Text variant="titleMedium" style={{ color: colors.onSurface }}>
          麦克风权限
        </Text>
        <Text
          variant="bodyMedium"
          style={[
            styles.permissionStatus,
            { color: hasPermission ? colors.primary : colors.error },
          ]}
        >
          {hasPermission === null
            ? '检查中...'
            : hasPermission
            ? '已授权'
            : '未授权'}
        </Text>
        {!hasPermission && (
          <Button mode="contained" onPress={requestPermission} style={styles.permissionButton}>
            请求权限
          </Button>
        )}
      </View>

      <Divider />

      {/* 基本设置 */}
      <List.Section>
        <List.Subheader>基本设置</List.Subheader>
        <List.Item
          title="自动启动语音"
          description="进入语音页面时自动开始监听"
          right={() => (
            <Switch
              value={settings.autoStart}
              onValueChange={(value) => saveSettings({ autoStart: value })}
            />
          )}
        />
        <List.Item
          title="连续对话"
          description="AI 回复后自动继续监听"
          right={() => (
            <Switch
              value={settings.continuousListening}
              onValueChange={(value) => saveSettings({ continuousListening: value })}
            />
          )}
        />
        <List.Item
          title="唤醒词"
          description="说出「小爱同学」唤醒（即将上线）"
          right={() => (
            <Switch
              value={settings.wakeWordEnabled}
              onValueChange={(value) => saveSettings({ wakeWordEnabled: value })}
              disabled
            />
          )}
        />
      </List.Section>

      <Divider />

      {/* 语音识别设置 */}
      <List.Section>
        <List.Subheader>语音识别</List.Subheader>
        <List.Item
          title="识别语言"
          description={LANGUAGE_OPTIONS.find((l) => l.value === settings.language)?.label}
          right={(props) => <List.Icon {...props} icon="chevron-right" />}
          onPress={() => setShowLanguageDialog(true)}
        />
      </List.Section>

      <Divider />

      {/* VAD 设置 */}
      <List.Section>
        <List.Subheader>语音检测 (VAD)</List.Subheader>
        <View style={styles.sliderContainer}>
          <View style={styles.sliderHeader}>
            <Text variant="bodyMedium" style={{ color: colors.onSurface }}>
              灵敏度
            </Text>
            <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
              {Math.round(settings.vadThreshold * 100)}%
            </Text>
          </View>
          <Slider
            value={settings.vadThreshold}
            onValueChange={(value) => saveSettings({ vadThreshold: value })}
            minimumValue={0.05}
            maximumValue={0.5}
            step={0.05}
            style={styles.slider}
          />
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            较高的值会降低误触发，但可能漏掉轻声说话
          </Text>
        </View>

        <View style={styles.sliderContainer}>
          <View style={styles.sliderHeader}>
            <Text variant="bodyMedium" style={{ color: colors.onSurface }}>
              静音超时
            </Text>
            <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
              {settings.silenceTimeout}ms
            </Text>
          </View>
          <Slider
            value={settings.silenceTimeout}
            onValueChange={(value) => saveSettings({ silenceTimeout: Math.round(value) })}
            minimumValue={500}
            maximumValue={3000}
            step={100}
            style={styles.slider}
          />
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            检测到静音后多久结束录音
          </Text>
        </View>
      </List.Section>

      <Divider />

      {/* 重置按钮 */}
      <View style={styles.resetContainer}>
        <Button
          mode="outlined"
          onPress={() => {
            setSettings(DEFAULT_SETTINGS);
            AsyncStorage.setItem('voice_settings', JSON.stringify(DEFAULT_SETTINGS));
          }}
        >
          恢复默认设置
        </Button>
      </View>

      <View style={styles.bottomPadding} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  permissionCard: {
    padding: 20,
    gap: 8,
  },
  permissionStatus: {
    marginTop: 4,
  },
  permissionButton: {
    marginTop: 12,
  },
  sliderContainer: {
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  sliderHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  slider: {
    marginVertical: 8,
  },
  resetContainer: {
    padding: 20,
    alignItems: 'center',
  },
  bottomPadding: {
    height: 40,
  },
});
