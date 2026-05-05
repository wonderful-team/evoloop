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
        setTestDetectedWord(`错误: ${error.message}`);
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
      setTestDetectedWord(`启动失败: ${error.message}`);
      setTestState('idle');
    }
  }, [testState, testService, wakeWord]);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <Header title="唤醒词设置" showBack />
      <ScrollView>
        {/* 唤醒词文本输入 */}
        <View style={styles.section}>
          <Text variant="titleMedium" style={{ color: colors.onSurface, marginBottom: 8 }}>
            唤醒词文本
          </Text>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant, marginBottom: 12 }}>
            说出以下词语即可唤醒语音助手（2-4 个字效果最好）
          </Text>
          <TextInput
            mode="outlined"
            value={wakeWord}
            onChangeText={(text) => setSetting('wakeWord', text)}
            placeholder="输入唤醒词"
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
            测试唤醒词
          </Text>
          <Button
            mode={testState === 'idle' ? 'contained' : 'outlined'}
            onPress={handleTest}
            icon={testState === 'idle' ? 'microphone' : 'stop'}
            loading={testState === 'listening'}
          >
            {testState === 'idle' && '开始测试'}
            {testState === 'listening' && '监听中... (10秒)'}
            {testState === 'detected' && '停止测试'}
          </Button>
          {testDetectedWord ? (
            <Text
              variant="bodyMedium"
              style={{ color: colors.primary, marginTop: 12, textAlign: 'center' }}
            >
              {testDetectedWord.startsWith('错误:') || testDetectedWord.startsWith('启动失败:')
                ? testDetectedWord
                : `检测到: 「${testDetectedWord}」`}
            </Text>
          ) : null}
        </View>

        <Divider />

        {/* 模型文件说明 */}
        <View style={styles.section}>
          <Text variant="titleMedium" style={{ color: colors.onSurface, marginBottom: 8 }}>
            模型文件配置
          </Text>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            唤醒词使用 Sherpa-ONNX 流式 ASR 引擎，模型文件需打包到 App 中：{'\n\n'}
            <Text style={{ fontWeight: 'bold' }}>1. 下载模型</Text>{'\n'}
            <Text
              style={{ color: colors.primary, textDecorationLine: 'underline' }}
              onPress={() => Linking.openURL('https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models')}
            >
              sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23
            </Text>{'\n'}
            约 25MB（int8 量化）{'\n\n'}
            <Text style={{ fontWeight: 'bold' }}>2. 放入项目</Text>{'\n'}
            Android: 放入 android/app/src/main/assets/sherpa-asr/{'\n'}
            iOS: 拖入 Xcode → Build Phases → Copy Bundle Resources{'\n\n'}
            <Text style={{ fontWeight: 'bold' }}>3. 快捷脚本</Text>{'\n'}
            <Text style={{ fontFamily: 'monospace', fontSize: 11 }}>
              bash scripts/download-sherpa-asr-model.sh
            </Text>
          </Text>
        </View>

        <Divider />

        {/* 后台监听说明 */}
        <View style={styles.section}>
          <Text variant="titleMedium" style={{ color: colors.onSurface, marginBottom: 8 }}>
            后台监听
          </Text>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            开启后，即使 App 退到后台也能监听唤醒词。{'\n'}
            {'\n'}
            <Text style={{ fontWeight: 'bold' }}>iOS:</Text> 退到后台后自动继续监听。{'\n'}
            <Text style={{ fontWeight: 'bold' }}>Android:</Text> 退到后台后会显示通知栏提示。{'\n'}
            {'\n'}
            注意：后台监听会增加电量消耗。如果不需要后台唤醒，建议关闭此功能。
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
