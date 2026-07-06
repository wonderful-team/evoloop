import React from 'react';
import { View, StyleSheet, ScrollView, Linking } from 'react-native';
import { List, Divider, Text, Card, Avatar } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '@/theme';
import { Header } from '@/components/common/Header';
import DeviceInfo from 'react-native-device-info';
import { useTranslation } from 'react-i18next';
import { BASE_URL } from '@/constants/config';

export default function AboutScreen() {
  const { t } = useTranslation();
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
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <Header title={t('settings.about.title')} showBack />
      <ScrollView>
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
            {t('settings.about.versionPrefix')} {appVersion} ({buildNumber})
          </Text>
        </View>

      <Divider />

      {/* 应用介绍 */}
      <Card style={styles.introCard}>
        <Card.Content>
          <Text variant="bodyMedium" style={{ color: colors.onSurface }}>
            {t('settings.about.intro')}
          </Text>
        </Card.Content>
      </Card>

      <Divider />

      {/* 链接 */}
      <List.Section>
        <List.Subheader>{t('settings.about.links')}</List.Subheader>
        <List.Item
          title={t('settings.about.officialWebsite')}
          description={t('settings.about.websiteUrl')}
          left={(props) => <List.Icon {...props} icon="web" />}
          right={(props) => <List.Icon {...props} icon="open-in-new" />}
          onPress={openWebsite}
        />
        <List.Item
          title={t('settings.about.github')}
          description={t('settings.about.viewSource')}
          left={(props) => <List.Icon {...props} icon="github" />}
          right={(props) => <List.Icon {...props} icon="open-in-new" />}
          onPress={openGithub}
        />
        <List.Item
          title={t('settings.about.feedback')}
          description="support@develop-assistant.cn"
          left={(props) => <List.Icon {...props} icon="email" />}
          right={(props) => <List.Icon {...props} icon="open-in-new" />}
          onPress={openFeedback}
        />
      </List.Section>

      <Divider />

      {/* 技术信息 */}
      <List.Section>
        <List.Subheader>{t('settings.about.techInfo')}</List.Subheader>
        <List.Item
          title={t('settings.about.reactNative')}
          description="0.76.9"
          left={(props) => <List.Icon {...props} icon="react" />}
        />
        <List.Item
          title={t('settings.about.architecture')}
          description={t('settings.about.bareWorkflow')}
          left={(props) => <List.Icon {...props} icon="code-tags" />}
        />
      </List.Section>

      <Divider />

      {/* 版权信息 */}
      <View style={styles.footer}>
        <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
          {t('settings.about.copyright')}
        </Text>
        <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
          {t('settings.about.madeWithLove')}
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
