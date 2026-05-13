// 用户协议组件 - 可复用于登录、注册等页面

import React from 'react';
import { View, StyleSheet, Linking } from 'react-native';
import { Text, Checkbox } from 'react-native-paper';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';
import { BASE_URL } from '@/constants/config';

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
  termsUrl = `${BASE_URL}/member/agreement/terms`,
  privacyUrl = `${BASE_URL}/member/agreement/privacy`,
  style,
}: UserAgreementProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();

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
        {t('auth.agree')}
        <Text style={{ color: colors.primary }} onPress={handleOpenTerms}>
          {t('auth.termsOfService')}
        </Text>
        {t('auth.and')}
        <Text style={{ color: colors.primary }} onPress={handleOpenPrivacy}>
          {t('auth.privacyPolicy')}
        </Text>
      </Text>
    </View>
  );
}

/**
 * 用户协议提示文本（用于弹窗等场景）
 */
export function UserAgreementText({
  termsUrl = `${BASE_URL}/member/agreement/terms`,
  privacyUrl = `${BASE_URL}/member/agreement/privacy`,
}: Omit<UserAgreementProps, 'agreed' | 'onToggle' | 'style'>) {
  const { colors } = useTheme();
  const { t } = useTranslation();

  return (
    <Text>
      {t('auth.pleaseAgreeFirst')}
      <Text style={{ color: colors.primary }} onPress={() => Linking.openURL(termsUrl)}>
        {t('auth.termsOfService')}
      </Text>
      {t('auth.and')}
      <Text style={{ color: colors.primary }} onPress={() => Linking.openURL(privacyUrl)}>
        {t('auth.privacyPolicy')}
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
