import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';
import MainNavigator from './MainNavigator';
import AuthNavigator from './AuthNavigator';
import LoginScreen from '../screens/auth/LoginScreen';
import RegisterScreen from '../screens/auth/RegisterScreen';
import ForgotPasswordScreen from '../screens/auth/ForgotPasswordScreen';
import BindMobileScreen from '../screens/auth/BindMobileScreen';
import ChatScreen from '../screens/ChatScreen';
import DevicesScreen from '../screens/DevicesScreen';
import ProjectsScreen from '../screens/ProjectsScreen';
import ProfileScreen from '../screens/ProfileScreen';
import SettingsScreen from '../screens/SettingsScreen';
import SettingsVoiceScreen from '../screens/SettingsVoiceScreen';
import SettingsAccountScreen from '../screens/SettingsAccountScreen';
import SettingsAboutScreen from '../screens/SettingsAboutScreen';
import WakeWordSettingsScreen from '../screens/WakeWordSettingsScreen';
import HelpScreen from '../screens/HelpScreen';
import PlansScreen from '../screens/PlansScreen';
import PayConfirmScreen from '../screens/PayConfirmScreen';
import PayResultScreen from '../screens/PayResultScreen';
import CloudChatScreen from '../screens/CloudChatScreen';

import DebugScreen from '../screens/DebugScreen';

const Stack = createStackNavigator();

export default function RootNavigator() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {/* 主功能区 */}
      <Stack.Screen name="Main" component={MainNavigator} />
      
      {/* 认证区 - 从下往上滑出 */}
      <Stack.Screen
        name="Auth"
        component={AuthNavigator}
        options={{
          animation: 'slide_from_bottom',
        }}
      />
      <Stack.Screen name="Login" component={LoginScreen} />
      <Stack.Screen name="Register" component={RegisterScreen} />
      <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
      <Stack.Screen name="BindMobile" component={BindMobileScreen} />
      
      {/* 核心功能页 */}

      <Stack.Screen name="CloudChat" component={CloudChatScreen} />
      <Stack.Screen name="CloudChatNew" component={CloudChatScreen} initialParams={{ id: 'new' }} />
      
      {/* 设置相关 */}
      <Stack.Screen name="Settings" component={SettingsScreen} />
      <Stack.Screen name="SettingsVoice" component={SettingsVoiceScreen} />
      <Stack.Screen name="SettingsAccount" component={SettingsAccountScreen} />
      <Stack.Screen name="SettingsAbout" component={SettingsAboutScreen} />
      <Stack.Screen name="SettingsWakeWord" component={WakeWordSettingsScreen} />
      
      {/* 订阅相关 */}
      <Stack.Screen name="Plans" component={PlansScreen} />
      <Stack.Screen name="PayConfirm" component={PayConfirmScreen} />
      <Stack.Screen name="PayResult" component={PayResultScreen} />
      
      {/* 其它 */}
      <Stack.Screen name="Help" component={HelpScreen} />
      <Stack.Screen name="Profile" component={ProfileScreen} />
      <Stack.Screen name="Devices" component={DevicesScreen} />
      <Stack.Screen name="Projects" component={ProjectsScreen} />

      {/* 调试测试 */}
      <Stack.Screen name="Debug" component={DebugScreen} />

    </Stack.Navigator>
  );
}
