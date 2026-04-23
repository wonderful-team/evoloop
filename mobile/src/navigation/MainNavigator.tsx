import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useAuthStore } from '@/stores/authStore';
import { router } from '@/utils/navigation';
import { useTheme } from '@/components/ui/ThemeProvider';

// 占位屏幕（稍后将被真实组件替换）
import ChatScreen from '../screens/ChatScreen';
import DevicesScreen from '../screens/DevicesScreen';
import ProjectsScreen from '../screens/ProjectsScreen';
import ProfileScreen from '../screens/ProfileScreen';

const Tab = createBottomTabNavigator();

export default function MainNavigator() {
  const { theme } = useTheme();
  const { isLoggedIn } = useAuthStore();

  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: theme.colors.primary,
        tabBarInactiveTintColor: theme.colors.onSurfaceVariant,
        tabBarStyle: {
          display: 'none', // 保持原项目隐藏 TabBar 的设计
        },
        headerShown: false,
      }}
    >
      <Tab.Screen name="index" component={ChatScreen} />
      
      <Tab.Screen 
        name="devices" 
        component={DevicesScreen}
        listeners={{
          tabPress: (e) => {
            if (!isLoggedIn) {
              e.preventDefault();
              router.push('Auth');
            }
          },
        }}
      />
      
      <Tab.Screen 
        name="projects" 
        component={ProjectsScreen}
        listeners={{
          tabPress: (e) => {
            if (!isLoggedIn) {
              e.preventDefault();
              router.push('Auth');
            }
          },
        }}
      />
      
      <Tab.Screen
        name="profile"
        component={ProfileScreen}
        listeners={{
          tabPress: (e) => {
            if (!isLoggedIn) {
              e.preventDefault();
              router.push('Auth');
            }
          },
        }}
      />
    </Tab.Navigator>
  );
}
