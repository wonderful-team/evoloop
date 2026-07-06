// 账号与安全设置页面

import React, { useState, useEffect } from 'react';
import { View, StyleSheet, ScrollView, Alert, Image, TouchableOpacity } from 'react-native';
import { List, Divider, Text, Button, TextInput, Portal, Dialog } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
import { Header } from '@/components/common/Header';
import { useAuthStore } from '@/stores/authStore';
import { authApi } from '@/services/api/auth';
import { AuthManager } from '@/services/auth/AuthManager';
import { useTheme as usePaperTheme } from 'react-native-paper';
import { RegisterConfig } from '@/types';

// 解析逗号分隔的配置字符串
function parseConfigValue(value: string | undefined): string[] {
  if (!value) return [];
  return value.split(',').map((s) => s.trim()).filter(Boolean);
}

// 根据 pwd_complexity 校验密码
function validatePasswordComplexity(password: string, complexity: string, t: any): string | null {
  if (!complexity) return null;
  const requirements = parseConfigValue(complexity);
  const errors: string[] = [];

  if (requirements.includes('number') && !/\d/.test(password)) {
    errors.push(t('settings.account.number'));
  }
  if (requirements.includes('letter') && !/[a-z]/.test(password)) {
    errors.push(t('settings.account.lowercase'));
  }
  if (requirements.includes('upper_case') && !/[A-Z]/.test(password)) {
    errors.push(t('settings.account.uppercase'));
  }
  if (requirements.includes('symbol') && !/[!@#$%^&*()_+\-=\[\]{};'"\\|,.<>\/?]/.test(password)) {
    errors.push(t('settings.account.specialChar'));
  }

  if (errors.length > 0) {
    return `${t('settings.account.passwordComplexityPrefix')}${errors.join(t('common.listSeparator'))}`;
  }
  return null;
}

export default function AccountSettingsScreen() {
  const { t } = useTranslation();
  const { theme } = useTheme(); const colors = theme.colors;
  const { userInfo } = useAuthStore();

  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [showPhoneDialog, setShowPhoneDialog] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [smsKey, setSmsKey] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [countdown, setCountdown] = useState(0);

  // 图形验证码（绑定手机号强制显示，不读配置 — 与 mobile_uniapp 一致）
  const [captchaId, setCaptchaId] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');

  // 注册配置（用于密码修改校验规则）
  const [registerConfig, setRegisterConfig] = useState<RegisterConfig | null>(null);

  // 加载注册配置（修改密码用）
  useEffect(() => {
    loadRegisterConfig();
  }, []);

  // 打开绑定手机对话框时加载验证码
  useEffect(() => {
    if (showPhoneDialog) {
      refreshCaptcha();
    }
  }, [showPhoneDialog]);

  // 加载注册配置
  const loadRegisterConfig = async () => {
    try {
      const config = await AuthManager.getRegisterConfig();
      setRegisterConfig(config);
    } catch (error: any) {
      console.error('获取注册配置失败:', error);
    }
  };

  // 获取密码最小长度
  const getMinPasswordLength = (): number => {
    if (!registerConfig || registerConfig.pwd_len <= 0) return 6;
    return registerConfig.pwd_len;
  };

  const refreshCaptcha = async () => {
    try {
      let captcha;
      if (captchaId) {
        captcha = await AuthManager.getCaptcha(captchaId);
      } else {
        captcha = await AuthManager.getCaptchaSimple();
      }
      if (captcha && captcha.img) {
        setCaptchaId(captcha.id);
        setCaptchaImage(captcha.img);
      }
    } catch (error) {
      console.error('刷新验证码失败:', error);
    }
  };

  // 修改密码
  const handleChangePassword = async () => {
    const minPwdLen = getMinPasswordLength();

    if (newPassword.length < minPwdLen) {
      Alert.alert(t('common.error.title'), t('settings.account.passwordLengthError', { min: minPwdLen }));
      return;
    }

    // 密码复杂度校验
    if (registerConfig?.pwd_complexity) {
      const complexityError = validatePasswordComplexity(newPassword, registerConfig.pwd_complexity, t);
      if (complexityError) {
        Alert.alert(t('common.error.title'), complexityError);
        return;
      }
    }

    if (newPassword !== confirmPassword) {
      Alert.alert(t('common.error.title'), t('auth.errors.passwordMismatch'));
      return;
    }

    setIsLoading(true);
    try {
      await authApi.modifyPassword({
        old_password: currentPassword,
        new_password: newPassword,
      });
      Alert.alert(t('common.success'), t('settings.account.passwordChanged'));
      setShowPasswordDialog(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (error: any) {
      Alert.alert(t('common.error.title'), error.message || t('settings.account.passwordChangeFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  // 发送验证码
  const sendVerificationCode = async () => {
    if (!newPhone || newPhone.length !== 11) {
      Alert.alert(t('common.error.title'), t('auth.errors.invalidMobile'));
      return;
    }

    if (!captchaCode) {
      Alert.alert(t('common.error.title'), t('auth.errors.captchaRequired'));
      return;
    }

    setIsLoading(true);
    try {
      const result = await authApi.sendBindMobileCode(
        newPhone,
        captchaCode,
        captchaId
      );
      if (result && result.key) {
        setSmsKey(result.key);
      }
      setCountdown(60);
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } catch (error: any) {
      Alert.alert(t('common.error.title'), error.message || t('settings.account.sendCodeFailed'));
      refreshCaptcha();
    } finally {
      setIsLoading(false);
    }
  };

  // 绑定手机
  const handleBindPhone = async () => {
    if (!smsCode || smsCode.length !== 6) {
      Alert.alert(t('common.error.title'), t('settings.account.enter6DigitCode'));
      return;
    }

    setIsLoading(true);
    try {
      await authApi.modifyMobile({
        mobile: newPhone,
        code: smsCode,
        key: smsKey,
      });
      Alert.alert(t('common.success'), t('settings.account.phoneBound'));
      setShowPhoneDialog(false);
      setNewPhone('');
      setSmsCode('');
      setCaptchaCode('');
    } catch (error: any) {
      Alert.alert(t('common.error.title'), error.message || t('settings.account.phoneBindFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <Header title={t('settings.account.title')} showBack />
      <ScrollView>
        {/* 账号信息 */}
      <List.Section>
        <List.Subheader>{t('settings.account.info')}</List.Subheader>
        <List.Item
          title={t('settings.account.userName')}
          description={userInfo?.nickname || t('settings.account.notSet')}
          left={(props) => <List.Icon {...props} icon="account" />}
        />
        <List.Item
          title={t('settings.account.phoneNumber')}
          description={userInfo?.mobile || t('settings.account.notBound')}
          left={(props) => <List.Icon {...props} icon="phone" />}
          right={(props) => (
            <Button
              mode="text"
              onPress={() => setShowPhoneDialog(true)}
              disabled={!!userInfo?.mobile}
            >
              {userInfo?.mobile ? t('settings.account.bound') : t('settings.account.bind')}
            </Button>
          )}
        />
        <List.Item
          title={t('settings.account.email')}
          description={userInfo?.email || t('settings.account.notBound')}
          left={(props) => <List.Icon {...props} icon="email" />}
        />
      </List.Section>

      <Divider />

      {/* 安全设置 */}
      <List.Section>
        <List.Subheader>{t('settings.account.security')}</List.Subheader>
        <List.Item
          title={t('settings.account.changePassword')}
          description={t('settings.account.changePasswordDesc')}
          left={(props) => <List.Icon {...props} icon="lock" />}
          right={(props) => <List.Icon {...props} icon="chevron-right" />}
          onPress={() => setShowPasswordDialog(true)}
        />
        <List.Item
          title={t('settings.account.deviceManagement')}
          description={t('settings.account.deviceManagementDesc')}
          left={(props) => <List.Icon {...props} icon="devices" />}
          right={(props) => <List.Icon {...props} icon="chevron-right" />}
          onPress={() => Alert.alert(t('settings.account.tip'), t('settings.account.comingSoon'))}
        />
      </List.Section>

      <Divider />

      {/* 危险操作 */}
      <List.Section>
        <List.Subheader>{t('settings.account.dangerZone')}</List.Subheader>
        <List.Item
          title={t('settings.account.deleteAccount')}
          titleStyle={{ color: colors.error }}
          description={t('settings.account.deleteAccountDesc')}
          left={(props) => (
            <List.Icon {...props} icon="delete-forever" color={colors.error} />
          )}
          onPress={() => {
            Alert.alert(
              t('settings.account.confirmDeleteAccount'),
              t('settings.account.deleteAccountWarning'),
              [
                { text: t('common.cancel'), style: 'cancel' },
                { text: t('settings.account.confirmDelete'), style: 'destructive', onPress: () => {} },
              ]
            );
          }}
        />
      </List.Section>

      {/* 修改密码对话框 */}
      <Portal>
        <Dialog visible={showPasswordDialog} onDismiss={() => setShowPasswordDialog(false)}>
          <Dialog.Title>{t('settings.account.changePassword')}</Dialog.Title>
          <Dialog.Content>
            <TextInput
              label={t('settings.account.currentPassword')}
              value={currentPassword}
              onChangeText={setCurrentPassword}
              secureTextEntry
              style={styles.input}
            />
            <TextInput
              label={t('settings.account.newPassword')}
              value={newPassword}
              onChangeText={setNewPassword}
              secureTextEntry
              style={styles.input}
            />
            <TextInput
              label={t('settings.account.confirmNewPassword')}
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              secureTextEntry
              style={styles.input}
            />
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowPasswordDialog(false)}>{t('common.cancel')}</Button>
            <Button onPress={handleChangePassword} loading={isLoading}>
              {t('common.confirm')}
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      {/* 绑定手机对话框 */}
      <Portal>
        <Dialog visible={showPhoneDialog} onDismiss={() => setShowPhoneDialog(false)}>
          <Dialog.Title>{t('settings.account.bindPhoneTitle')}</Dialog.Title>
          <Dialog.Content>
            <TextInput
              label={t('settings.account.mobileLabel')}
              value={newPhone}
              onChangeText={setNewPhone}
              keyboardType="phone-pad"
              maxLength={11}
              style={styles.input}
            />

            {/* 图形验证码 — 与 mobile_uniapp 一致，始终显示 */}
            <View style={styles.captchaContainer}>
              <TextInput
                label={t('settings.account.captchaLabel')}
                value={captchaCode}
                onChangeText={setCaptchaCode}
                style={[styles.input, styles.captchaInput]}
              />
              <TouchableOpacity onPress={refreshCaptcha} style={styles.captchaImage}>
                {captchaImage ? (
                  <Image
                    source={{ uri: captchaImage }}
                    style={styles.captchaImg}
                    resizeMode="cover"
                  />
                ) : (
                  <Text style={{ color: colors.onSurfaceVariant }}>{t('settings.account.refreshCaptcha')}</Text>
                )}
              </TouchableOpacity>
            </View>

            <View style={styles.codeInputContainer}>
              <TextInput
                label={t('settings.account.verificationCode')}
                value={smsCode}
                onChangeText={setSmsCode}
                keyboardType="number-pad"
                maxLength={6}
                style={[styles.input, styles.codeInput]}
              />
              <Button
                mode="outlined"
                onPress={sendVerificationCode}
                disabled={countdown > 0 || isLoading || !captchaCode}
                style={styles.sendCodeButton}
              >
                {countdown > 0 ? t('common.secondsShort', { count: countdown }) : t('settings.account.getCode')}
              </Button>
            </View>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowPhoneDialog(false)}>{t('common.cancel')}</Button>
            <Button onPress={handleBindPhone} loading={isLoading}>
              {t('settings.account.bind')}
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      <View style={styles.bottomPadding} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  input: {
    marginVertical: 8,
  },
  captchaContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginVertical: 8,
  },
  captchaInput: {
    flex: 1,
  },
  captchaImage: {
    width: 100,
    height: 44,
    borderRadius: 8,
    overflow: 'hidden',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f0f0f0',
  },
  captchaImg: {
    width: '100%',
    height: '100%',
  },
  codeInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginTop: 8,
  },
  codeInput: {
    flex: 1,
  },
  sendCodeButton: {
    marginTop: 8,
  },
  bottomPadding: {
    height: 40,
  },
});
