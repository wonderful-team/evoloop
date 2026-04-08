// 主应用路由组布局 - 底部 Tab 导航
// 首页允许游客访问，设备和项目需要登录

import { Tabs, usePathname, useRouter } from 'expo-router';
import { MaterialIcons } from '@expo/vector-icons';
import { useTheme } from '@/components/ui/ThemeProvider';
import { useAuthStore } from '@/stores/authStore';

export default function MainLayout() {
  const { theme } = useTheme();
  const { isLoggedIn } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();

  // Tab 按压处理 - 未登录时跳转到登录页
  const handleTabPress = (routeName: string) => {
    if ((routeName === 'devices' || routeName === 'projects') && !isLoggedIn) {
      router.push('/(auth)/login');
      return false;
    }
    return true;
  };

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: theme.colors.primary,
        tabBarInactiveTintColor: theme.colors.onSurfaceVariant,
        tabBarStyle: {
          display: 'none', // 隐藏底部导航栏
        },
        headerShown: false,
      }}
    >
      {/* 首页 - 语音对话 - 允许游客 */}
      <Tabs.Screen
        name="index"
        options={{
          title: '首页',
          tabBarIcon: ({ color, size }) => (
            <MaterialIcons name="chat" size={size} color={color} />
          ),
        }}
      />
      
      {/* 设备列表 - 需要登录 */}
      <Tabs.Screen
        name="devices"
        options={{
          title: '设备',
          tabBarIcon: ({ color, size }) => (
            <MaterialIcons name="desktop-mac" size={size} color={color} />
          ),
        }}
        listeners={{
          tabPress: (e) => {
            if (!isLoggedIn) {
              e.preventDefault();
              router.push('/(auth)/login');
            }
          },
        }}
      />
      
      {/* 项目列表 - 需要登录 */}
      <Tabs.Screen
        name="projects"
        options={{
          title: '项目',
          tabBarIcon: ({ color, size }) => (
            <MaterialIcons name="folder" size={size} color={color} />
          ),
        }}
        listeners={{
          tabPress: (e) => {
            if (!isLoggedIn) {
              e.preventDefault();
              router.push('/(auth)/login');
            }
          },
        }}
      />
      
      {/* 个人中心 */}
      <Tabs.Screen
        name="profile"
        options={{
          title: '我的',
          tabBarIcon: ({ color, size }) => (
            <MaterialIcons name="person" size={size} color={color} />
          ),
        }}
      />
      
      {/* 语音页面 - 不在 Tab 显示 */}
      <Tabs.Screen
        name="voice"
        options={{
          href: null,
        }}
      />
    </Tabs>
  );
}
