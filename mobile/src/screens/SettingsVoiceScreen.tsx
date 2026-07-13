// 语音设置页面

import React, { useState, useEffect } from 'react';
import { View, StyleSheet, ScrollView } from 'react-native';
import { List, Switch, Divider, Text, Button, IconButton } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
import { Header } from '@/components/common/Header';
import { AudioRecorder } from '@/services/voice/AudioRecorder';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getDefaultVoices } from '@/hooks/useTTS';

interface VoiceSettings {
  autoStart: boolean;
  continuousListening: boolean;
  vadThreshold: number;
  silenceTimeout: number;
  language: string;
}

const DEFAULT_SETTINGS: VoiceSettings = {
  autoStart: false,
  continuousListening: true,
  vadThreshold: 0.15,
  silenceTimeout: 1500,
  language: 'zh-CN',
};

export default function VoiceSettingsScreen() {
  const { t } = useTranslation();

  const LANGUAGE_OPTIONS = [
    { value: 'zh-CN', label: t('settings.voice.langZhCN') },
    { value: 'en-US', label: t('settings.voice.langEnUS') },
    { value: 'zh-HK', label: t('settings.voice.langZhHK') },
    { value: 'ja-JP', label: t('settings.voice.langJaJP') },
  ];
  const { theme } = useTheme();
  const colors = theme.colors;
  const [settings, setSettings] = useState<VoiceSettings>(DEFAULT_SETTINGS);

  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [showLanguageDialog, setShowLanguageDialog] = useState(false);
  const [ttsVoice, setTtsVoice] = useState<string>('aimei');

  // 加载设置
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const savedSettings = await AsyncStorage.getItem('voice_settings');
        if (savedSettings) {
          setSettings({ ...DEFAULT_SETTINGS, ...JSON.parse(savedSettings) });
        }
        const savedTtsVoice = await AsyncStorage.getItem('evoloop_tts_voice');
        if (savedTtsVoice) {
          setTtsVoice(savedTtsVoice);
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

  // 保存 TTS 声音
  const saveTtsVoice = async (voice: string) => {
    setTtsVoice(voice);
    await AsyncStorage.setItem('evoloop_tts_voice', voice);
  };

  // 请求麦克风权限
  const requestPermission = async () => {
    const granted = await AudioRecorder.requestPermissions();
    setHasPermission(granted);
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <Header title={t('settings.voice.title')} showBack />
      <ScrollView>
        {/* 权限状态 */}
      <View style={styles.permissionCard}>
        <Text variant="titleMedium" style={{ color: colors.onSurface }}>
          {t('settings.voice.micPermission')}
        </Text>
        <Text
          variant="bodyMedium"
          style={[
            styles.permissionStatus,
            { color: hasPermission ? colors.primary : colors.error },
          ]}
        >
          {hasPermission === null
            ? t('settings.voice.checking')
            : hasPermission
            ? t('settings.voice.authorized')
            : t('settings.voice.notAuthorized')}
        </Text>
        {!hasPermission && (
          <Button mode="contained" onPress={requestPermission} style={styles.permissionButton}>
            {t('settings.voice.requestPermission')}
          </Button>
        )}
      </View>

      <Divider />

      {/* 基本设置 */}
      <List.Section>
        <List.Subheader>{t('settings.voice.basicSettings')}</List.Subheader>
        <List.Item
          title={t('settings.voice.autoStart')}
          description={t('settings.voice.autoStartDesc')}
          right={() => (
            <Switch
              value={settings.autoStart}
              onValueChange={(value) => saveSettings({ autoStart: value })}
            />
          )}
        />
        <List.Item
          title={t('settings.voice.continuousListening')}
          description={t('settings.voice.continuousListeningDesc')}
          right={() => (
            <Switch
              value={settings.continuousListening}
              onValueChange={(value) => saveSettings({ continuousListening: value })}
            />
          )}
        />
      </List.Section>

      <Divider />

      {/* 语音识别设置 */}
      <List.Section>
        <List.Subheader>{t('settings.voice.speechRecognition')}</List.Subheader>
        <List.Item
          title={t('settings.voice.language')}
          description={LANGUAGE_OPTIONS.find((l) => l.value === settings.language)?.label}
          right={(props) => <List.Icon {...props} icon="chevron-right" />}
          onPress={() => setShowLanguageDialog(true)}
        />
      </List.Section>

      <Divider />

      {/* TTS 语音合成设置 */}
      <List.Section>
        <List.Subheader>{t('settings.voice.tts')}</List.Subheader>
        {getDefaultVoices(t).map((voice) => (
          <List.Item
            key={voice.id}
            title={voice.name}
            description={voice.description}
            right={(props) =>
              ttsVoice === voice.id ? (
                <List.Icon {...props} icon="check" color={colors.primary} />
              ) : null
            }
            onPress={() => saveTtsVoice(voice.id)}
          />
        ))}
      </List.Section>

      <Divider />

      {/* VAD 设置 */}
      <List.Section>
        <List.Subheader>{t('settings.voice.vad')}</List.Subheader>
        <View style={styles.sliderContainer}>
          <View style={styles.sliderHeader}>
            <Text variant="bodyMedium" style={{ color: colors.onSurface }}>
              {t('settings.voice.vadThreshold')}
            </Text>
            <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
              {Math.round(settings.vadThreshold * 100)}{t('common.units.percent')}
            </Text>
          </View>
          <View style={styles.stepperRow}>
            <IconButton
              icon="minus"
              size={20}
              onPress={() => saveSettings({ vadThreshold: Math.max(0.05, Math.round((settings.vadThreshold - 0.05) * 100) / 100) })}
            />
            <View style={[styles.stepperTrack, { backgroundColor: colors.surfaceVariant }]}>
              <View
                style={[
                  styles.stepperFill,
                  {
                    backgroundColor: colors.primary,
                    width: `${((settings.vadThreshold - 0.05) / 0.45) * 100}%`,
                  },
                ]}
              />
            </View>
            <IconButton
              icon="plus"
              size={20}
              onPress={() => saveSettings({ vadThreshold: Math.min(0.5, Math.round((settings.vadThreshold + 0.05) * 100) / 100) })}
            />
          </View>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            {t('settings.voice.sensitivityDesc')}
          </Text>
        </View>

        <View style={styles.sliderContainer}>
          <View style={styles.sliderHeader}>
            <Text variant="bodyMedium" style={{ color: colors.onSurface }}>
              {t('settings.voice.silenceTimeout')}
            </Text>
            <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
              {settings.silenceTimeout}ms
            </Text>
          </View>
          <View style={styles.stepperRow}>
            <IconButton
              icon="minus"
              size={20}
              onPress={() => saveSettings({ silenceTimeout: Math.max(500, settings.silenceTimeout - 100) })}
            />
            <View style={[styles.stepperTrack, { backgroundColor: colors.surfaceVariant }]}>
              <View
                style={[
                  styles.stepperFill,
                  {
                    backgroundColor: colors.primary,
                    width: `${((settings.silenceTimeout - 500) / 2500) * 100}%`,
                  },
                ]}
              />
            </View>
            <IconButton
              icon="plus"
              size={20}
              onPress={() => saveSettings({ silenceTimeout: Math.min(3000, settings.silenceTimeout + 100) })}
            />
          </View>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            {t('settings.voice.silenceTimeoutDesc')}
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
          {t('settings.voice.reset')}
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
  stepperRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginVertical: 8,
  },
  stepperTrack: {
    flex: 1,
    height: 8,
    borderRadius: 4,
    marginHorizontal: 8,
    overflow: 'hidden',
  },
  stepperFill: {
    height: '100%',
    borderRadius: 4,
  },
  resetContainer: {
    padding: 20,
    alignItems: 'center',
  },
  bottomPadding: {
    height: 40,
  },
});
