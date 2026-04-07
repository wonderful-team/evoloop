// 账号与安全设置页面

import React, { useState } from 'react';
import { View, StyleSheet, ScrollView, Alert } from 'react-native';
import { List, Divider, Text, Button, TextInput, Portal, Dialog } from 'react-native-paper';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/components/ui/ThemeProvider';
import { useAuthStore } from '@/stores/authStore';
import { authApi } from '@/services/api/auth';

export default function AccountSettingsScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const { user } = useAuthStore();

  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [showPhoneDialog, setShowPhoneDialog] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [countdown, setCountdown] = useState(0);

  // 修改密码
  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      Alert.alert('错误', '两次输入的密码不一致');
      return;
    }

    if (newPassword.length < 6) {
      Alert.alert('错误', '密码长度至少为6位');
      return;
    }

    setIsLoading(true);
    try {
      await authApi.changePassword(currentPassword, newPassword);
      Alert.alert('成功', '密码已修改');
      setShowPasswordDialog(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (error) {
      Alert.alert('错误', '密码修改失败，请检查当前密码');
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

    setIsLoading(true);
    try {
      await authApi.sendSmsCode(newPhone);
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
    } catch (error) {
      Alert.alert('错误', '发送验证码失败');
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
      await authApi.bindMobile(newPhone, smsCode);
      Alert.alert('成功', '手机号绑定成功');
      setShowPhoneDialog(false);
      setNewPhone('');
      setSmsCode('');
    } catch (error) {
      Alert.alert('错误', '绑定失败，请检查验证码');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.colors.background }]}
    >
      {/* 账号信息 */}
      <List.Section>
        <List.Subheader>账号信息</List.Subheader>
        <List.Item
          title="用户名"
          description={user?.username || '未设置'}
          left={(props) => <List.Icon {...props} icon="account" />}
        />
        <List.Item
          title="手机号"
          description={user?.mobile || '未绑定'}
          left={(props) => <List.Icon {...props} icon="phone" />}
          right={(props) => (
            <Button
              mode="text"
              onPress={() => setShowPhoneDialog(true)}
              disabled={!!user?.mobile}
            >
              {user?.mobile ? '已绑定' : '绑定'}
            </Button>
          )}
        />
        <List.Item
          title="邮箱"
          description={user?.email || '未绑定'}
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
          titleStyle={{ color: colors.colors.error }}
          description="永久删除账号及所有数据"
          left={(props) => (
            <List.Icon {...props} icon="delete-forever" color={colors.colors.error} />
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
                disabled={countdown > 0 || isLoading}
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
  codeInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
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
