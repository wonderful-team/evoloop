// 设置主页面

import React from 'react';
import { View, StyleSheet, ScrollView, Linking } from 'react-native';
import { List, Divider, Text, Avatar } from 'react-native-paper';
import { useRouter } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { useTheme } from '@/components/ui/ThemeProvider';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function SettingsScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { colors } = useTheme();
  const { user, logout } = useAuthStore();

  const handleLogout = async () => {
    await logout();
    router.replace('/(auth)/login');
  };

  const openPrivacyPolicy = () => {
    Linking.openURL('https://evoloop.develop-assistant.cn/privacy');
  };

  const openTermsOfService = () => {
    Linking.openURL('https://evoloop.develop-assistant.cn/terms');
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.colors.background }]}>
      <ScrollView>
        {/* 用户信息卡片 */}
        <View style={styles.userCard}>
          <Avatar.Text
            size={64}
            label={user?.username?.substring(0, 2)?.toUpperCase() || '?'}
            style={{ backgroundColor: colors.colors.primary }}
          />
          <View style={styles.userInfo}>
            <Text variant="titleMedium" style={{ color: colors.colors.onSurface }}>
              {user?.username || t('profile.guestTitle')}
            </Text>
            <Text variant="bodySmall" style={{ color: colors.colors.onSurfaceVariant }}>
              {user?.mobile || user?.email || ''}
            </Text>
          </View>
        </View>

        <Divider />

        {/* 功能设置 */}
        <List.Section>
          <List.Subheader>功能设置</List.Subheader>
          <List.Item
            title="语音设置"
            description="语音识别、对话偏好"
            left={(props) => <List.Icon {...props} icon="microphone" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('/settings/voice')}
          />
          <List.Item
            title="账号与安全"
            description="修改密码、绑定手机"
            left={(props) => <List.Icon {...props} icon="shield-account" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('/settings/account')}
          />
        </List.Section>

        <Divider />

        {/* 通用设置 */}
        <List.Section>
          <List.Subheader>通用</List.Subheader>
          <List.Item
            title="新手引导"
            description="重新查看应用介绍"
            left={(props) => <List.Icon {...props} icon="school" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('/onboarding')}
          />
          <List.Item
            title="帮助与反馈"
            description="查看帮助文档或联系我们"
            left={(props) => <List.Icon {...props} icon="help-circle" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('/help')}
          />
          <List.Item
            title="关于"
            description="版本信息、隐私政策"
            left={(props) => <List.Icon {...props} icon="information" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('/settings/about')}
          />
        </List.Section>

        <Divider />

        {/* 法律信息 */}
        <List.Section>
          <List.Subheader>法律信息</List.Subheader>
          <List.Item
            title="隐私政策"
            left={(props) => <List.Icon {...props} icon="file-document-outline" />}
            onPress={openPrivacyPolicy}
          />
          <List.Item
            title="服务条款"
            left={(props) => <List.Icon {...props} icon="file-document-outline" />}
            onPress={openTermsOfService}
          />
        </List.Section>

        <Divider />

        {/* 退出登录 */}
        {user && (
          <List.Section>
            <List.Item
              title="退出登录"
              titleStyle={{ color: colors.colors.error }}
              left={(props) => (
                <List.Icon {...props} icon="logout" color={colors.colors.error} />
              )}
              onPress={handleLogout}
            />
          </List.Section>
        )}

        <View style={styles.versionInfo}>
          <Text variant="bodySmall" style={{ color: colors.colors.onSurfaceVariant }}>
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
