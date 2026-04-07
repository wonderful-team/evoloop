// 登录入口页面

import { View, StyleSheet, Image } from 'react-native';
import { useEffect } from 'react';
import { router } from 'expo-router';
import { Button, Text } from 'react-native-paper';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '@/theme';
import { MaterialIcons } from '@expo/vector-icons';

export default function AuthIndex() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const { isLoggedIn } = useAuthStore();
  
  // 如果已登录，跳转到首页
  useEffect(() => {
    if (isLoggedIn) {
      router.replace('/(main)');
    }
  }, [isLoggedIn]);
  
  const goToLogin = () => {
    router.push('/(auth)/login');
  };

  const goToRegister = () => {
    router.push('/(auth)/register');
  };
  
  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.content}>
        {/* Logo 区域 */}
        <View style={styles.logoContainer}>
          <View style={[styles.logo, { backgroundColor: colors.primary }]}>
            <MaterialIcons name="smart-toy" size={64} color="#fff" />
          </View>
          <Text variant="headlineLarge" style={[styles.title, { color: colors.primary }]}>
            EvoLoop
          </Text>
          <Text variant="bodyLarge" style={[styles.subtitle, { color: colors.text.secondary }]}>
            {t('index.subtitle')}
          </Text>
        </View>
        
        {/* 功能介绍 */}
        <View style={styles.features}>
          <View style={styles.featureItem}>
            <MaterialIcons name="mic" size={24} color={colors.primary} />
            <Text variant="bodyMedium" style={styles.featureText}>
              语音对话控制
            </Text>
          </View>
          <View style={styles.featureItem}>
            <MaterialIcons name="desktop-mac" size={24} color={colors.primary} />
            <Text variant="bodyMedium" style={styles.featureText}>
              远程设备管理
            </Text>
          </View>
          <View style={styles.featureItem}>
            <MaterialIcons name="folder" size={24} color={colors.primary} />
            <Text variant="bodyMedium" style={styles.featureText}>
              项目多端同步
            </Text>
          </View>
        </View>
        
        {/* 按钮区域 */}
        <View style={styles.buttonContainer}>
          <Button
            mode="contained"
            onPress={goToLogin}
            style={styles.button}
            contentStyle={styles.buttonContent}
            icon={({ size, color }) => (
              <MaterialIcons name="login" size={size} color={color} />
            )}
          >
            {t('auth.login.title')}
          </Button>

          <Button
            mode="outlined"
            onPress={goToRegister}
            style={styles.button}
            contentStyle={styles.buttonContent}
            icon={({ size, color }) => (
              <MaterialIcons name="person-add" size={size} color={color} />
            )}
          >
            注册账号
          </Button>
        </View>

        {/* 底部提示 */}
        <Text variant="bodySmall" style={[styles.terms, { color: colors.text.tertiary }]}>
          登录即表示您同意我们的服务协议和隐私政策
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  logoContainer: {
    alignItems: 'center',
    marginBottom: 48,
  },
  logo: {
    width: 120,
    height: 120,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
    elevation: 8,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 8,
  },
  subtitle: {
    textAlign: 'center',
    opacity: 0.8,
  },
  features: {
    width: '100%',
    marginBottom: 48,
    gap: 16,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  featureText: {
    opacity: 0.8,
  },
  buttonContainer: {
    width: '100%',
    maxWidth: 300,
    gap: 12,
  },
  button: {
    borderRadius: 8,
  },
  buttonContent: {
    paddingVertical: 8,
  },
  terms: {
    marginTop: 24,
    textAlign: 'center',
  },
});
