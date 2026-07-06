// 唤醒词设置页面（Sherpa-ONNX ASR 版本）

import React, { useState, useCallback, useEffect } from 'react';
import { View, StyleSheet, ScrollView, Linking } from 'react-native';
import { Text, Button, TextInput, Divider, Chip } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '@/theme';
import { Header } from '@/components/common/Header';
import { useSettingsStore } from '@/stores/settingsStore';
import { WakeWordService } from '@/services/voice/WakeWordService';
import { useTranslation } from 'react-i18next';

// Spoken wake-word phrases; language-specific config values, intentionally not translated.
const PRESET_WAKE_WORDS = [
  '木头人',
  '你好 EvoLoop',
  '小 Evo',
  'EvoLoop',
];

export default function WakeWordSettingsScreen() {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const colors = theme.colors;

  const settings = useSettingsStore((state) => state.settings);
  const setSetting = useSettingsStore((state) => state.setSetting);

  const [testState, setTestState] = useState<'idle' | 'listening' | 'detected'>('idle');
  const [testService, setTestService] = useState<WakeWordService | null>(null);
  const [testDetectedWord, setTestDetectedWord] = useState('');

  const wakeWord = settings.wakeWord;

  // 组件卸载时自动停止测试服务
  useEffect(() => {
    return () => {
      if (testService?.getIsStarted()) {
        testService.stop().catch(() => {});
      }
    };
  }, [testService]);

  const handleTest = useCallback(async () => {
    if (testState === 'listening' || testState === 'detected') {
      await testService?.stop();
      setTestService(null);
      setTestState('idle');
      return;
    }

    setTestState('listening');
    setTestDetectedWord('');

    const service = new WakeWordService({
      wakeWord,
      onWake: (text) => {
        setTestDetectedWord(text);
        setTestState('detected');
        setTimeout(() => {
          setTestState('idle');
        }, 3000);
      },
      onError: (error) => {
        setTestDetectedWord(`${t('settings.voice.errorPrefix')} ${error.message}`);
        setTestState('idle');
      },
    });

    try {
      await service.start();
      setTestService(service);

      // 10 秒超时自动停止
      setTimeout(async () => {
        if (service.getIsStarted()) {
          await service.stop();
          setTestService(null);
          setTestState((prev) => (prev === 'listening' ? 'idle' : prev));
        }
      }, 10000);
    } catch (error: any) {
      setTestDetectedWord(`${t('settings.voice.startFailedPrefix')} ${error.message}`);
      setTestState('idle');
    }
  }, [testState, testService, wakeWord, t]);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <Header title={t('settings.voice.wakeWordSettingsTitle')} showBack />
      <ScrollView>
        {/* 唤醒词文本输入 */}
        <View style={styles.section}>
          <Text variant="titleMedium" style={{ color: colors.onSurface, marginBottom: 8 }}>
            {t('settings.voice.wakeWordText')}
          </Text>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant, marginBottom: 12 }}>
            {t('settings.voice.wakeWordHint')}
          </Text>
          <TextInput
            mode="outlined"
            value={wakeWord}
            onChangeText={(text) => setSetting('wakeWord', text)}
            placeholder={t('settings.voice.wakeWordPlaceholder')}
            style={{ backgroundColor: colors.surface }}
          />

          {/* 预设唤醒词 */}
          <View style={styles.chipRow}>
            {PRESET_WAKE_WORDS.map((word) => (
              <Chip
                key={word}
                selected={wakeWord === word}
                onPress={() => setSetting('wakeWord', word)}
                style={[
                  styles.chip,
                  wakeWord === word && { backgroundColor: colors.primaryContainer },
                ]}
                textStyle={
                  wakeWord === word ? { color: colors.primary } : { color: colors.onSurface }
                }
              >
                {word}
              </Chip>
            ))}
          </View>
        </View>

        <Divider />

        {/* 测试唤醒词 */}
        <View style={styles.section}>
          <Text variant="titleMedium" style={{ color: colors.onSurface, marginBottom: 8 }}>
            {t('settings.voice.wakeWordTest')}
          </Text>
          <Button
            mode={testState === 'idle' ? 'contained' : 'outlined'}
            onPress={handleTest}
            icon={testState === 'idle' ? 'microphone' : 'stop'}
            loading={testState === 'listening'}
          >
            {testState === 'idle' && t('settings.voice.startTest')}
            {testState === 'listening' && t('settings.voice.listening')}
            {testState === 'detected' && t('settings.voice.stopTest')}
          </Button>
          {testDetectedWord ? (
            <Text
              variant="bodyMedium"
              style={{ color: colors.primary, marginTop: 12, textAlign: 'center' }}
            >
              {testDetectedWord.startsWith(t('settings.voice.errorPrefix')) || testDetectedWord.startsWith(t('settings.voice.startFailedPrefix'))
                ? testDetectedWord
                : t('settings.voice.detected', { word: testDetectedWord })}
            </Text>
          ) : null}
        </View>

        <Divider />

        {/* 模型文件说明 */}
        <View style={styles.section}>
          <Text variant="titleMedium" style={{ color: colors.onSurface, marginBottom: 8 }}>
            {t('settings.voice.modelConfigTitle')}
          </Text>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            {t('settings.voice.modelConfigDesc')}{'\n\n'}
            <Text style={{ fontWeight: 'bold' }}>{t('settings.voice.downloadModel')}</Text>{'\n'}
            <Text
              style={{ color: colors.primary, textDecorationLine: 'underline' }}
              onPress={() => Linking.openURL('https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models')}
            >
              sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23
            </Text>{'\n'}
            {t('settings.voice.modelSize')}{'\n\n'}
            <Text style={{ fontWeight: 'bold' }}>{t('settings.voice.putInProject')}</Text>{'\n'}
            {t('settings.voice.androidPath')}{'\n'}
            {t('settings.voice.iosPath')}{'\n\n'}
            <Text style={{ fontWeight: 'bold' }}>{t('settings.voice.quickScript')}</Text>{'\n'}
            <Text style={{ fontFamily: 'monospace', fontSize: 11 }}>
              bash scripts/download-sherpa-asr-model.sh
            </Text>
          </Text>
        </View>

        <Divider />

        {/* 后台监听说明 */}
        <View style={styles.section}>
          <Text variant="titleMedium" style={{ color: colors.onSurface, marginBottom: 8 }}>
            {t('settings.voice.backgroundListenTitle')}
          </Text>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            {t('settings.voice.backgroundListenDesc')}{'\n'}
            {'\n'}
            <Text style={{ fontWeight: 'bold' }}>{t('common.ios')}:</Text> {t('settings.voice.iosNote')}{'\n'}
            <Text style={{ fontWeight: 'bold' }}>{t('common.android')}:</Text> {t('settings.voice.androidNote')}{'\n'}
            {'\n'}
            {t('settings.voice.batteryWarning')}
          </Text>
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
  section: {
    padding: 20,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 12,
  },
  chip: {
    marginRight: 8,
    marginBottom: 8,
  },
  bottomPadding: {
    height: 40,
  },
});
