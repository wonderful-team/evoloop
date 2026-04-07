// 关于页面

import React from 'react';
import { View, StyleSheet, ScrollView, Linking } from 'react-native';
import { List, Divider, Text, Button, Card, Avatar } from 'react-native-paper';
import { useTheme } from '@/components/ui/ThemeProvider';
import Constants from 'expo-constants';

export default function AboutScreen() {
  const { colors } = useTheme();
  const appVersion = Constants.expoConfig?.version || '1.0.0';
  const buildNumber = Constants.expoConfig?.ios?.buildNumber || '1';

  const openWebsite = () => {
    Linking.openURL('https://evoloop.develop-assistant.cn');
  };

  const openGithub = () => {
    Linking.openURL('https://github.com/evoloop');
  };

  const openFeedback = () => {
    Linking.openURL('mailto:support@develop-assistant.cn');
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.colors.background }]}
    >
      {/* 应用信息 */}
      <View style={styles.header}>
        <Avatar.Text
          size={100}
          label="E"
          style={{ backgroundColor: colors.colors.primary, marginBottom: 16 }}
          labelStyle={{ fontSize: 48, fontWeight: 'bold' }}
        />
        <Text variant="headlineMedium" style={{ color: colors.colors.onSurface }}>
          EvoLoop
        </Text>
        <Text variant="bodyMedium" style={{ color: colors.colors.onSurfaceVariant }}>
          版本 {appVersion} ({buildNumber})
        </Text>
      </View>

      <Divider />

      {/* 应用介绍 */}
      <Card style={styles.introCard}>
        <Card.Content>
          <Text variant="bodyMedium" style={{ color: colors.colors.onSurface }}>
            EvoLoop 是您的随身通用 AI 智能体。通过简单的语音对话，即可管理设备、获取答案、执行任务。
            支持云端智能和本地设备控制的无缝切换。
          </Text>
        </Card.Content>
      </Card>

      <Divider />

      {/* 链接 */}
      <List.Section>
        <List.Subheader>链接</List.Subheader>
        <List.Item
          title="官方网站"
          description="evoloop.develop-assistant.cn"
          left={(props) => <List.Icon {...props} icon="web" />}
          right={(props) => <List.Icon {...props} icon="open-in-new" />}
          onPress={openWebsite}
        />
        <List.Item
          title="GitHub"
          description="查看开源代码"
          left={(props) => <List.Icon {...props} icon="github" />}
          right={(props) => <List.Icon {...props} icon="open-in-new" />}
          onPress={openGithub}
        />
        <List.Item
          title="反馈建议"
          description="support@develop-assistant.cn"
          left={(props) => <List.Icon {...props} icon="email" />}
          right={(props) => <List.Icon {...props} icon="open-in-new" />}
          onPress={openFeedback}
        />
      </List.Section>

      <Divider />

      {/* 技术信息 */}
      <List.Section>
        <List.Subheader>技术信息</List.Subheader>
        <List.Item
          title="React Native"
          description={Constants.expoConfig?.sdkVersion || '0.76'}
          left={(props) => <List.Icon {...props} icon="react" />}
        />
        <List.Item
          title="Expo SDK"
          description="52.0"
          left={(props) => <List.Icon {...props} icon="code-tags" />}
        />
      </List.Section>

      <Divider />

      {/* 版权信息 */}
      <View style={styles.footer}>
        <Text variant="bodySmall" style={{ color: colors.colors.onSurfaceVariant }}>
          © 2024 EvoLoop. All rights reserved.
        </Text>
        <Text variant="bodySmall" style={{ color: colors.colors.onSurfaceVariant }}>
          Made with ❤️ by Develop Assistant Team
        </Text>
      </View>

      <View style={styles.bottomPadding} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    alignItems: 'center',
    paddingVertical: 40,
    gap: 12,
  },
  introCard: {
    margin: 16,
    elevation: 0,
  },
  footer: {
    alignItems: 'center',
    paddingVertical: 24,
    gap: 4,
  },
  bottomPadding: {
    height: 40,
  },
});
