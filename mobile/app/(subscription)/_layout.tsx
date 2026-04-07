// 订阅路由组布局

import { Stack } from 'expo-router';

export default function SubscriptionLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: true,
        headerBackTitle: '返回',
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen 
        name="plans" 
        options={{ title: '订阅管理' }}
      />
      <Stack.Screen 
        name="pay-confirm" 
        options={{ title: '确认支付', headerShown: false }}
      />
      <Stack.Screen 
        name="pay-result" 
        options={{ title: '支付结果', headerBackVisible: false }}
      />
    </Stack>
  );
}
