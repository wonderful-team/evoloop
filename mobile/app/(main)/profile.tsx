// 个人中心页面

import { View, StyleSheet } from 'react-native';
import { Text, Button, List, Avatar } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { useTheme } from '@/components/ui/ThemeProvider';
import { router } from 'expo-router';
import { maskMobile } from '@/utils/format';
import { MaterialIcons } from '@expo/vector-icons';

// 游客模式下的个人中心
function GuestProfile() {
  const { t } = useTranslation();
  const { toggleTheme, isDark } = useTheme();
  
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <View style={styles.guestAvatar}>
          <MaterialIcons name="person-outline" size={48} color="#9CA3AF" />
        </View>
        <Text variant="titleLarge" style={styles.name}>
          游客
        </Text>
        <Text variant="bodyMedium" style={styles.mobile}>
          登录后可以使用更多功能
        </Text>
        <Button
          mode="contained"
          style={styles.loginButton}
          onPress={() => router.push('/(auth)/login')}
        >
          立即登录
        </Button>
      </View>
      
      <List.Section>
        <List.Item
          title={t('profile.language')}
          left={props => <List.Icon {...props} icon="translate" />}
          right={props => <Text>{t('profile.chinese')}</Text>}
        />
        <List.Item
          title={isDark ? '深色模式' : '浅色模式'}
          left={props => <List.Icon {...props} icon={isDark ? 'moon-waning-crescent' : 'white-balance-sunny'} />}
          onPress={toggleTheme}
        />
        <List.Item
          title={t('profile.manual')}
          left={props => <List.Icon {...props} icon="help-circle" />}
          right={props => <List.Icon {...props} icon="chevron-right" />}
          onPress={() => router.push('/help')}
        />
      </List.Section>
    </SafeAreaView>
  );
}

// 登录用户的个人中心
function UserProfile() {
  const { t } = useTranslation();
  const { userInfo, logout } = useAuthStore();
  const { toggleTheme, isDark } = useTheme();
  
  const handleLogout = () => {
    logout();
    router.replace('/(auth)');
  };
  
  const goToSubscription = () => {
    router.push('/(subscription)/plans');
  };
  
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Avatar.Text
          size={80}
          label={userInfo?.nickname?.slice(0, 2) || 'U'}
          style={styles.avatar}
        />
        <Text variant="titleLarge" style={styles.name}>
          {userInfo?.nickname || userInfo?.mobile}
        </Text>
        <Text variant="bodyMedium" style={styles.mobile}>
          {maskMobile(userInfo?.mobile || '')}
        </Text>
      </View>
      
      <List.Section>
        <List.Item
          title="设置"
          left={props => <List.Icon {...props} icon="cog" />}
          right={props => <List.Icon {...props} icon="chevron-right" />}
          onPress={() => router.push('/settings')}
        />
        <List.Item
          title={t('profile.manageSubscription')}
          left={props => <List.Icon {...props} icon="crown" />}
          right={props => <List.Icon {...props} icon="chevron-right" />}
          onPress={goToSubscription}
        />
        <List.Item
          title={t('profile.language')}
          left={props => <List.Icon {...props} icon="translate" />}
          right={props => <Text>{t('profile.chinese')}</Text>}
        />
        <List.Item
          title={isDark ? '深色模式' : '浅色模式'}
          left={props => <List.Icon {...props} icon={isDark ? 'moon-waning-crescent' : 'white-balance-sunny'} />}
          onPress={toggleTheme}
        />
        <List.Item
          title={t('profile.manual')}
          left={props => <List.Icon {...props} icon="help-circle" />}
          right={props => <List.Icon {...props} icon="chevron-right" />}
          onPress={() => router.push('/help')}
        />
      </List.Section>
      
      <View style={styles.footer}>
        <Button mode="outlined" onPress={handleLogout} style={styles.logoutButton}>
          {t('profile.logout')}
        </Button>
      </View>
    </SafeAreaView>
  );
}

export default function ProfileScreen() {
  const { isLoggedIn } = useAuthStore();
  
  if (!isLoggedIn) {
    return <GuestProfile />;
  }
  
  return <UserProfile />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    alignItems: 'center',
    padding: 32,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.1)',
  },
  avatar: {
    marginBottom: 16,
  },
  guestAvatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#F3F4F6',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  name: {
    fontWeight: 'bold',
    marginBottom: 4,
  },
  mobile: {
    opacity: 0.6,
    textAlign: 'center',
  },
  loginButton: {
    marginTop: 16,
    minWidth: 200,
  },
  footer: {
    padding: 16,
    marginTop: 'auto',
  },
  logoutButton: {
    borderColor: 'red',
  },
});
