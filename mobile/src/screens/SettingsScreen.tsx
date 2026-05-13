import React from 'react';
import { View, StyleSheet, ScrollView, Linking } from 'react-native';
import { List, Divider, Text, Avatar } from 'react-native-paper';
import { router } from '@/utils/navigation';
import { useTranslation } from 'react-i18next';
import { Header } from '@/components/common/Header';
import { useAuthStore } from '@/stores/authStore';
import { useTheme } from '@/theme';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BASE_URL } from '@/constants/config';

export default function SettingsScreen() {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const colors = theme.colors;
  const { userInfo, logout } = useAuthStore();

  const handleLogout = async () => {
    await logout();
    router.replace('Auth');
  };

  const openPrivacyPolicy = () => {
    Linking.openURL(`${BASE_URL}/member/agreement/privacy`);
  };

  const openTermsOfService = () => {
    Linking.openURL(`${BASE_URL}/member/agreement/terms`);
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <Header title={t('settings.title')} showBack />
      <ScrollView>
        {/* 用户信息卡片 */}
        <View style={styles.userCard}>
          <Avatar.Text
            size={64}
            label={userInfo?.nickname?.substring(0, 2)?.toUpperCase() || '?'}
            style={{ backgroundColor: colors.primary }}
          />
          <View style={styles.userInfo}>
            <Text variant="titleMedium" style={{ color: colors.onSurface }}>
              {userInfo?.nickname || t('profile.guestTitle')}
            </Text>
            <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
              {userInfo?.mobile || ''}
            </Text>
          </View>
        </View>

        <Divider />

        {/* 功能设置 */}
        <List.Section>
          <List.Subheader>{t('settings.featureSettings')}</List.Subheader>
          <List.Item
            title={t('settings.voice.title')}
            description={t('settings.voice.autoStart')}
            left={(props) => <List.Icon {...props} icon="microphone" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('SettingsVoice')}
          />
          <List.Item
            title={t('settings.account.title')}
            description={t('settings.account.bindPhone')}
            left={(props) => <List.Icon {...props} icon="shield-account" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('SettingsAccount')}
          />
        </List.Section>

        <Divider />

        {/* 通用设置 */}
        <List.Section>
          <List.Subheader>{t('settings.general')}</List.Subheader>

          <List.Item
            title={t('settings.helpFeedback')}
            description={t('settings.helpFeedbackDesc')}
            left={(props) => <List.Icon {...props} icon="help-circle" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('Help')}
          />
          <List.Item
            title={t('settings.about.title')}
            description={t('settings.about.termsOfService')}
            left={(props) => <List.Icon {...props} icon="information" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('SettingsAbout')}
          />
        </List.Section>

        <Divider />

        {/* 法律信息 */}
        <List.Section>
          <List.Subheader>{t('settings.legalInfo')}</List.Subheader>
          <List.Item
            title={t('settings.about.privacyPolicy')}
            left={(props) => <List.Icon {...props} icon="file-document-outline" />}
            onPress={openPrivacyPolicy}
          />
          <List.Item
            title={t('settings.about.termsOfService')}
            left={(props) => <List.Icon {...props} icon="file-document-outline" />}
            onPress={openTermsOfService}
          />
        </List.Section>

        <Divider />

        {/* 退出登录 */}
        {userInfo && (
          <List.Section>
            <List.Item
              title={t('settings.logout')}
              titleStyle={{ color: colors.error }}
              left={(props) => (
                <List.Icon {...props} icon="logout" color={colors.error} />
              )}
              onPress={handleLogout}
            />
          </List.Section>
        )}

        <View style={styles.versionInfo}>
          <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
            EvoLoop v1.0.0
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 24,
    gap: 16,
  },
  userInfo: {
    flex: 1,
    gap: 4,
  },
  versionInfo: {
    alignItems: 'center',
    padding: 24,
  },
});
