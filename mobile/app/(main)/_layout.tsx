// 主应用路由组布局 - 底部 Tab 导航
// 按 PRD 设计：4个 Tab（首页/设备/项目/我的）

import { Tabs } from 'expo-router';
import { MaterialIcons } from '@expo/vector-icons';
import { useTheme } from '@/components/ui/ThemeProvider';

export default function MainLayout() {
  const { theme } = useTheme();
  
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: theme.colors.primary,
        tabBarInactiveTintColor: theme.colors.onSurfaceVariant,
        tabBarStyle: {
          backgroundColor: theme.colors.surface,
          borderTopColor: theme.colors.outline,
          height: 60,
          paddingBottom: 8,
        },
        headerShown: false,
      }}
    >
      {/* 首页 - 语音对话 */}
      <Tabs.Screen
        name="index"
        options={{
          title: '首页',
          tabBarIcon: ({ color, size }) => (
            <MaterialIcons name="chat" size={size} color={color} />
          ),
        }}
      />
      
      {/* 设备列表 */}
      <Tabs.Screen
        name="devices"
        options={{
          title: '设备',
          tabBarIcon: ({ color, size }) => (
            <MaterialIcons name="desktop-mac" size={size} color={color} />
          ),
        }}
      />
      
      {/* 项目列表 */}
      <Tabs.Screen
        name="projects"
        options={{
          title: '项目',
          tabBarIcon: ({ color, size }) => (
            <MaterialIcons name="folder" size={size} color={color} />
          ),
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
      
      {/* 语音页面 - 不在 Tab 显示（已合并到首页） */}
      <Tabs.Screen
        name="voice"
        options={{
          href: null,
        }}
      />
    </Tabs>
  );
}
