// 设置页面布局

import { Stack } from 'expo-router';
import { useTheme } from '@/components/ui/ThemeProvider';

export default function SettingsLayout() {
  const { theme } = useTheme();

  return (
    <Stack
      screenOptions={{
        headerStyle: {
          backgroundColor: theme.colors.background,
        },
        headerTintColor: theme.colors.onSurface,
        headerTitleStyle: {
          fontWeight: '600',
        },
        headerShadowVisible: false,
      }}
    >
      <Stack.Screen
        name="index"
        options={{
          title: '设置',
        }}
      />
      <Stack.Screen
        name="voice"
        options={{
          title: '语音设置',
        }}
      />
      <Stack.Screen
        name="account"
        options={{
          title: '账号与安全',
        }}
      />
      <Stack.Screen
        name="about"
        options={{
          title: '关于',
        }}
      />
    </Stack>
  );
}
