// 微信登录按钮组件

import React from 'react';
import { StyleSheet } from 'react-native';
import { Button } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';

interface WechatLoginButtonProps {
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
}

export function WechatLoginButton({
  onPress,
  disabled = false,
  loading = false,
}: WechatLoginButtonProps) {
  return (
    <Button
      mode="contained"
      onPress={onPress}
      disabled={disabled}
      loading={loading}
      icon={({ size, color }) => (
        <MaterialIcons name="wechat" size={size} color={color} />
      )}
      style={styles.button}
      contentStyle={styles.content}
      buttonColor="#07C160"
      textColor="#FFFFFF"
    >
      微信一键登录
    </Button>
  );
}

const styles = StyleSheet.create({
  button: {
    borderRadius: 8,
  },
  content: {
    height: 48,
  },
});
