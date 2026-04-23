// 用户协议组件 - 可复用于登录、注册等页面

import React from 'react';
import { View, StyleSheet, Linking } from 'react-native';
import { Text, Checkbox } from 'react-native-paper';
import { useTheme } from '@/theme';

interface UserAgreementProps {
  /** 是否已同意 */
  agreed: boolean;
  /** 切换同意状态 */
  onToggle: () => void;
  /** 服务协议 URL */
  termsUrl?: string;
  /** 隐私政策 URL */
  privacyUrl?: string;
  /** 自定义样式 */
  style?: object;
}

/**
 * 用户协议勾选组件
 * 包含复选框和可点击的协议链接
 */
export function UserAgreement({
  agreed,
  onToggle,
  termsUrl = 'https://evoloop.develop-assistant.cn/agreement/terms',
  privacyUrl = 'https://evoloop.develop-assistant.cn/agreement/privacy',
  style,
}: UserAgreementProps) {
  const { colors } = useTheme();

  const handleOpenTerms = () => {
    Linking.openURL(termsUrl);
  };

  const handleOpenPrivacy = () => {
    Linking.openURL(privacyUrl);
  };

  return (
    <View style={[styles.container, style]}>
      <Checkbox
        status={agreed ? 'checked' : 'unchecked'}
        onPress={onToggle}
      />
      <Text variant="bodySmall" style={styles.text}>
        我已阅读并同意
        <Text style={{ color: colors.primary }} onPress={handleOpenTerms}>
          《服务协议》
        </Text>
        和
        <Text style={{ color: colors.primary }} onPress={handleOpenPrivacy}>
          《隐私政策》
        </Text>
      </Text>
    </View>
  );
}

/**
 * 用户协议提示文本（用于弹窗等场景）
 */
export function UserAgreementText({
  termsUrl = 'https://evoloop.develop-assistant.cn/agreement/terms',
  privacyUrl = 'https://evoloop.develop-assistant.cn/agreement/privacy',
}: Omit<UserAgreementProps, 'agreed' | 'onToggle' | 'style'>) {
  const { colors } = useTheme();

  return (
    <Text>
      请先阅读并同意
      <Text style={{ color: colors.primary }} onPress={() => Linking.openURL(termsUrl)}>
        《服务协议》
      </Text>
      和
      <Text style={{ color: colors.primary }} onPress={() => Linking.openURL(privacyUrl)}>
        《隐私政策》
      </Text>
    </Text>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  text: {
    flex: 1,
    marginLeft: 8,
  },
});

export default UserAgreement;
