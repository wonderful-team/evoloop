import React from 'react';
import { View, StyleSheet, ScrollView, Linking } from 'react-native';
import { List, Divider, Text, Card, Avatar } from 'react-native-paper';
import { useTheme } from '@/theme';
import DeviceInfo from 'react-native-device-info';
import { BASE_URL } from '@/constants/config';

export default function AboutScreen() {
  const { theme } = useTheme();
  const colors = theme.colors;
  const appVersion = DeviceInfo.getVersion();
  const buildNumber = DeviceInfo.getBuildNumber();

  const openWebsite = () => {
    Linking.openURL(`${BASE_URL}/member`);
  };

  const openGithub = () => {
    Linking.openURL('https://github.com/evoloop');
  };

  const openFeedback = () => {
    Linking.openURL('mailto:support@develop-assistant.cn');
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.background }]}
    >
      {/* 应用信息 */}
      <View style={styles.header}>
        <Avatar.Text
          size={100}
          label="E"
          style={{ backgroundColor: colors.primary, marginBottom: 16 }}
          labelStyle={{ fontSize: 48, fontWeight: 'bold' }}
        />
        <Text variant="headlineMedium" style={{ color: colors.onSurface }}>
          EvoLoop
        </Text>
        <Text variant="bodyMedium" style={{ color: colors.onSurfaceVariant }}>
          版本 {appVersion} ({buildNumber})
        </Text>
      </View>

      <Divider />

      {/* 应用介绍 */}
      <Card style={styles.introCard}>
        <Card.Content>
          <Text variant="bodyMedium" style={{ color: colors.onSurface }}>
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
          description="www.evoloop.cn"
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
          description="0.76.9"
          left={(props) => <List.Icon {...props} icon="react" />}
        />
        <List.Item
          title="架构"
          description="Bare Workflow (Native)"
          left={(props) => <List.Icon {...props} icon="code-tags" />}
        />
      </List.Section>

      <Divider />

      {/* 版权信息 */}
      <View style={styles.footer}>
        <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
          © 2024 EvoLoop. All rights reserved.
        </Text>
        <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
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
