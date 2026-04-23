// 账号与安全设置页面

import React, { useState, useEffect } from 'react';
import { View, StyleSheet, ScrollView, Alert, Image, TouchableOpacity } from 'react-native';
import { List, Divider, Text, Button, TextInput, Portal, Dialog } from 'react-native-paper';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
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
function validatePasswordComplexity(password: string, complexity: string): string | null {
  if (!complexity) return null;
  const requirements = parseConfigValue(complexity);
  const errors: string[] = [];

  if (requirements.includes('number') && !/\d/.test(password)) {
    errors.push('数字');
  }
  if (requirements.includes('letter') && !/[a-z]/.test(password)) {
    errors.push('小写字母');
  }
  if (requirements.includes('upper_case') && !/[A-Z]/.test(password)) {
    errors.push('大写字母');
  }
  if (requirements.includes('symbol') && !/[!@#$%^&*()_+\-=\[\]{};'"\\|,.<>\/?]/.test(password)) {
    errors.push('特殊字符');
  }

  if (errors.length > 0) {
    return `密码需包含${errors.join('、')}`;
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
      Alert.alert('错误', `密码长度至少为${minPwdLen}位`);
      return;
    }

    // 密码复杂度校验
    if (registerConfig?.pwd_complexity) {
      const complexityError = validatePasswordComplexity(newPassword, registerConfig.pwd_complexity);
      if (complexityError) {
        Alert.alert('错误', complexityError);
        return;
      }
    }

    if (newPassword !== confirmPassword) {
      Alert.alert('错误', '两次输入的密码不一致');
      return;
    }

    setIsLoading(true);
    try {
      await authApi.modifyPassword({
        old_password: currentPassword,
        new_password: newPassword,
      });
      Alert.alert('成功', '密码已修改');
      setShowPasswordDialog(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (error: any) {
      Alert.alert('错误', error.message || '密码修改失败，请检查当前密码');
    } finally {
      setIsLoading(false);
    }
  };

  // 发送验证码
  const sendVerificationCode = async () => {
    if (!newPhone || newPhone.length !== 11) {
      Alert.alert('错误', '请输入正确的手机号');
      return;
    }

    if (!captchaCode) {
      Alert.alert('错误', '请输入图形验证码');
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
      Alert.alert('错误', error.message || '发送验证码失败');
      refreshCaptcha();
    } finally {
      setIsLoading(false);
    }
  };

  // 绑定手机
  const handleBindPhone = async () => {
    if (!smsCode || smsCode.length !== 6) {
      Alert.alert('错误', '请输入6位验证码');
      return;
    }

    setIsLoading(true);
    try {
      await authApi.modifyMobile({
        mobile: newPhone,
        code: smsCode,
        key: smsKey,
      });
      Alert.alert('成功', '手机号绑定成功');
      setShowPhoneDialog(false);
      setNewPhone('');
      setSmsCode('');
      setCaptchaCode('');
    } catch (error: any) {
      Alert.alert('错误', error.message || '绑定失败，请检查验证码');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.background }]}
    >
      {/* 账号信息 */}
      <List.Section>
        <List.Subheader>账号信息</List.Subheader>
        <List.Item
          title="用户名"
          description={userInfo?.nickname || '未设置'}
          left={(props) => <List.Icon {...props} icon="account" />}
        />
        <List.Item
          title="手机号"
          description={userInfo?.mobile || '未绑定'}
          left={(props) => <List.Icon {...props} icon="phone" />}
          right={(props) => (
            <Button
              mode="text"
              onPress={() => setShowPhoneDialog(true)}
              disabled={!!userInfo?.mobile}
            >
              {userInfo?.mobile ? '已绑定' : '绑定'}
            </Button>
          )}
        />
        <List.Item
          title="邮箱"
          description={userInfo?.email || '未绑定'}
          left={(props) => <List.Icon {...props} icon="email" />}
        />
      </List.Section>

      <Divider />

      {/* 安全设置 */}
      <List.Section>
        <List.Subheader>安全</List.Subheader>
        <List.Item
          title="修改密码"
          description="定期更换密码保护账号安全"
          left={(props) => <List.Icon {...props} icon="lock" />}
          right={(props) => <List.Icon {...props} icon="chevron-right" />}
          onPress={() => setShowPasswordDialog(true)}
        />
        <List.Item
          title="登录设备管理"
          description="查看和管理已登录的设备"
          left={(props) => <List.Icon {...props} icon="devices" />}
          right={(props) => <List.Icon {...props} icon="chevron-right" />}
          onPress={() => Alert.alert('提示', '功能开发中')}
        />
      </List.Section>

      <Divider />

      {/* 危险操作 */}
      <List.Section>
        <List.Subheader>危险操作</List.Subheader>
        <List.Item
          title="注销账号"
          titleStyle={{ color: colors.error }}
          description="永久删除账号及所有数据"
          left={(props) => (
            <List.Icon {...props} icon="delete-forever" color={colors.error} />
          )}
          onPress={() => {
            Alert.alert(
              '确认注销',
              '注销账号将永久删除您的所有数据，此操作无法撤销。是否继续？',
              [
                { text: '取消', style: 'cancel' },
                { text: '确认注销', style: 'destructive', onPress: () => {} },
              ]
            );
          }}
        />
      </List.Section>

      {/* 修改密码对话框 */}
      <Portal>
        <Dialog visible={showPasswordDialog} onDismiss={() => setShowPasswordDialog(false)}>
          <Dialog.Title>修改密码</Dialog.Title>
          <Dialog.Content>
            <TextInput
              label="当前密码"
              value={currentPassword}
              onChangeText={setCurrentPassword}
              secureTextEntry
              style={styles.input}
            />
            <TextInput
              label="新密码"
              value={newPassword}
              onChangeText={setNewPassword}
              secureTextEntry
              style={styles.input}
            />
            <TextInput
              label="确认新密码"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              secureTextEntry
              style={styles.input}
            />
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowPasswordDialog(false)}>取消</Button>
            <Button onPress={handleChangePassword} loading={isLoading}>
              确认
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      {/* 绑定手机对话框 */}
      <Portal>
        <Dialog visible={showPhoneDialog} onDismiss={() => setShowPhoneDialog(false)}>
          <Dialog.Title>绑定手机号</Dialog.Title>
          <Dialog.Content>
            <TextInput
              label="手机号"
              value={newPhone}
              onChangeText={setNewPhone}
              keyboardType="phone-pad"
              maxLength={11}
              style={styles.input}
            />

            {/* 图形验证码 — 与 mobile_uniapp 一致，始终显示 */}
            <View style={styles.captchaContainer}>
              <TextInput
                label="图形验证码"
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
                  <Text style={{ color: colors.onSurfaceVariant }}>点击刷新</Text>
                )}
              </TouchableOpacity>
            </View>

            <View style={styles.codeInputContainer}>
              <TextInput
                label="验证码"
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
                {countdown > 0 ? `${countdown}s` : '获取验证码'}
              </Button>
            </View>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowPhoneDialog(false)}>取消</Button>
            <Button onPress={handleBindPhone} loading={isLoading}>
              绑定
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      <View style={styles.bottomPadding} />
    </ScrollView>
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
