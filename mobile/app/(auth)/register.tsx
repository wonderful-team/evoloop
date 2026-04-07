// 注册页面 - 支持手机号注册和用户名注册

import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
} from 'react-native';
import {
  Text,
  TextInput,
  Button,
  Checkbox,
  Portal,
  Dialog,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useRouter } from 'expo-router';
import { useAuth } from '@/hooks/useAuth';
import { useTheme } from '@/theme';
import { CountdownButton, CaptchaImage } from '@/components/auth';
import { AuthManager } from '@/services/auth/AuthManager';
import { api } from '@/services/api/client';
import { MEMBER_API } from '@/constants/api';
import { validate } from '@/utils/validate';

type RegisterType = 'mobile' | 'username';

export default function RegisterScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { colors } = useTheme();
  const { sendMobileCode, isLoading } = useAuth();

  // 注册类型
  const [registerType, setRegisterType] = useState<RegisterType>('mobile');

  // 手机号注册表单
  const [mobile, setMobile] = useState('');
  const [mobileCode, setMobileCode] = useState('');
  const [mobileCodeKey, setMobileCodeKey] = useState('');
  const [mobilePassword, setMobilePassword] = useState('');
  const [showMobilePassword, setShowMobilePassword] = useState(false);

  // 用户名注册表单
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  // 图形验证码
  const [captchaId, setCaptchaId] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');
  const [needCaptcha, setNeedCaptcha] = useState(false);

  // 用户协议
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [showTermsDialog, setShowTermsDialog] = useState(false);

  // 表单错误
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [registerError, setRegisterError] = useState('');

  // 加载图形验证码配置
  useEffect(() => {
    loadCaptchaConfig();
  }, []);

  // 加载验证码配置
  const loadCaptchaConfig = async () => {
    try {
      const config = await AuthManager.getCaptchaConfig();
      console.log('Captcha config:', config);
      
      // 如果配置了需要验证码
      if (config && config.shop_reception_login === 1) {
        setNeedCaptcha(true);
        try {
          await refreshCaptcha();
        } catch (captchaError: any) {
          // 如果验证码服务不可用，暂时禁用验证码功能
          console.warn('验证码服务不可用，暂时禁用:', captchaError);
          setNeedCaptcha(false);
        }
      }
    } catch (error: any) {
      console.error('获取验证码配置失败:', error);
      // 获取配置失败时，暂时禁用验证码
      setNeedCaptcha(false);
    }
  };

  // 刷新图形验证码
  const refreshCaptcha = async () => {
    try {
      setFormErrors({});
      
      // 第一次获取验证码时不带 captchaId，刷新时带上旧的 captchaId
      let captcha;
      if (captchaId) {
        captcha = await AuthManager.getCaptcha(captchaId);
      } else {
        captcha = await AuthManager.getCaptchaSimple();
      }
      
      if (!captcha) {
        console.error('验证码响应为空');
        throw new Error('获取验证码失败，请重试');
      }
      
      if (!captcha.id || !captcha.img) {
        console.error('验证码数据不完整:', captcha);
        throw new Error('验证码数据不完整');
      }
      
      setCaptchaId(captcha.id);
      setCaptchaImage(captcha.img);
    } catch (error: any) {
      console.error('获取图形验证码失败:', error);
      // 如果验证码服务不可用，禁用验证码功能
      setNeedCaptcha(false);
      setFormErrors({ 
        captchaCode: error.message || '验证码服务暂时不可用' 
      });
    }
  };

  // 发送手机验证码
  const handleSendMobileCode = async () => {
    // 验证手机号
    if (!validate.mobile(mobile)) {
      setFormErrors({ mobile: '请输入正确的手机号' });
      return false;
    }

    // 如果需要图形验证码
    if (needCaptcha && !captchaCode) {
      setFormErrors({ captchaCode: '请输入图形验证码' });
      return false;
    }

    try {
      const result = await sendMobileCode(mobile, captchaId, captchaCode);
      if (result) {
        setMobileCodeKey(result.key);
        setFormErrors({});
        return true;
      }
    } catch (error: any) {
      setFormErrors({
        mobile: error.message || '发送验证码失败',
      });
      // 刷新验证码
      if (needCaptcha) {
        refreshCaptcha();
      }
    }
    return false;
  };

  // 手机号注册
  const handleMobileRegister = async () => {
    // 表单验证
    const errors: Record<string, string> = {};

    if (!validate.mobile(mobile)) {
      errors.mobile = '请输入正确的手机号';
    }
    if (!mobileCode) {
      errors.mobileCode = '请输入验证码';
    }
    if (!mobilePassword || mobilePassword.length < 6) {
      errors.mobilePassword = '密码至少6位';
    }
    if (needCaptcha && !captchaCode) {
      errors.captchaCode = '请输入图形验证码';
    }
    if (!agreedToTerms) {
      setShowTermsDialog(true);
      return;
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    setFormErrors({});
    setRegisterError('');

    try {
      const response = await api.post(MEMBER_API.SEND_MOBILE_CODE, {
        mobile,
        key: mobileCodeKey,
        code: mobileCode,
        password: mobilePassword,
      });

      if (response.data?.code === 0) {
        // 注册成功，跳转到登录页
        router.replace('/(auth)/login');
      } else {
        setRegisterError(response.data?.message || '注册失败');
      }
    } catch (error: any) {
      setRegisterError(error.message || '注册失败，请重试');
    }
  };

  // 用户名注册
  const handleUsernameRegister = async () => {
    // 表单验证
    const errors: Record<string, string> = {};

    if (!username.trim() || username.length < 3) {
      errors.username = '用户名至少3位';
    }
    if (!password || password.length < 6) {
      errors.password = '密码至少6位';
    }
    if (password !== confirmPassword) {
      errors.confirmPassword = '两次密码不一致';
    }
    if (needCaptcha && !captchaCode) {
      errors.captchaCode = '请输入图形验证码';
    }
    if (!agreedToTerms) {
      setShowTermsDialog(true);
      return;
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    setFormErrors({});
    setRegisterError('');

    try {
      // 调用用户名注册 API
      const response = await api.post('/api/register', {
        username,
        password,
        captcha_id: captchaId,
        captcha_code: captchaCode,
      });

      if (response.data?.code === 0) {
        // 注册成功，跳转到登录页
        router.replace('/(auth)/login');
      } else {
        setRegisterError(response.data?.message || '注册失败');
      }
    } catch (error: any) {
      setRegisterError(error.message || '注册失败，请重试');
    }
  };

  // 跳转到登录
  const goToLogin = () => {
    router.back();
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          {/* 标题 */}
          <View style={styles.header}>
            <Text variant="headlineLarge" style={[styles.title, { color: colors.primary }]}>
              注册账号
            </Text>
            <Text variant="bodyLarge" style={{ color: colors.text.secondary }}>
              创建您的 EvoLoop 账号
            </Text>
          </View>

          {/* 注册类型切换 */}
          <View style={styles.tabContainer}>
            <TouchableOpacity
              style={[
                styles.tab,
                registerType === 'mobile' && [styles.activeTab, { borderBottomColor: colors.primary }],
              ]}
              onPress={() => setRegisterType('mobile')}
            >
              <Text
                variant="titleMedium"
                style={[
                  styles.tabText,
                  { color: registerType === 'mobile' ? colors.primary : colors.text.secondary },
                ]}
              >
                手机注册
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[
                styles.tab,
                registerType === 'username' && [styles.activeTab, { borderBottomColor: colors.primary }],
              ]}
              onPress={() => setRegisterType('username')}
            >
              <Text
                variant="titleMedium"
                style={[
                  styles.tabText,
                  { color: registerType === 'username' ? colors.primary : colors.text.secondary },
                ]}
              >
                用户名注册
              </Text>
            </TouchableOpacity>
          </View>

          {/* 手机号注册表单 */}
          {registerType === 'mobile' && (
            <View style={styles.form}>
              <TextInput
                label="手机号"
                value={mobile}
                onChangeText={(text) => {
                  setMobile(text);
                  if (formErrors.mobile) {
                    setFormErrors((prev) => ({ ...prev, mobile: '' }));
                  }
                }}
                keyboardType="phone-pad"
                maxLength={11}
                error={!!formErrors.mobile}
                left={<TextInput.Affix text="+86 " />}
                style={styles.input}
              />
              {formErrors.mobile && (
                <Text style={[styles.errorText, { color: colors.error }]}>
                  {formErrors.mobile}
                </Text>
              )}

              {/* 图形验证码 */}
              {needCaptcha && (
                <View style={styles.captchaContainer}>
                  <TextInput
                    label="图形验证码"
                    value={captchaCode}
                    onChangeText={setCaptchaCode}
                    error={!!formErrors.captchaCode}
                    style={[styles.input, styles.captchaInput]}
                  />
                  <CaptchaImage
                    captchaId={captchaId}
                    captchaImage={captchaImage}
                    onRefresh={refreshCaptcha}
                  />
                </View>
              )}
              {formErrors.captchaCode && (
                <Text style={[styles.errorText, { color: colors.error }]}>
                  {formErrors.captchaCode}
                </Text>
              )}

              <View style={styles.codeContainer}>
                <TextInput
                  label="短信验证码"
                  value={mobileCode}
                  onChangeText={(text) => {
                    setMobileCode(text);
                    if (formErrors.mobileCode) {
                      setFormErrors((prev) => ({ ...prev, mobileCode: '' }));
                    }
                  }}
                  keyboardType="number-pad"
                  maxLength={6}
                  error={!!formErrors.mobileCode}
                  style={[styles.input, styles.codeInput]}
                />
                <CountdownButton
                  onPress={handleSendMobileCode}
                  disabled={!validate.mobile(mobile) || (needCaptcha && !captchaCode)}
                />
              </View>
              {formErrors.mobileCode && (
                <Text style={[styles.errorText, { color: colors.error }]}>
                  {formErrors.mobileCode}
                </Text>
              )}

              <TextInput
                label="设置密码"
                value={mobilePassword}
                onChangeText={(text) => {
                  setMobilePassword(text);
                  if (formErrors.mobilePassword) {
                    setFormErrors((prev) => ({ ...prev, mobilePassword: '' }));
                  }
                }}
                secureTextEntry={!showMobilePassword}
                error={!!formErrors.mobilePassword}
                style={styles.input}
                right={
                  <TextInput.Icon
                    icon={showMobilePassword ? 'eye-off' : 'eye'}
                    onPress={() => setShowMobilePassword(!showMobilePassword)}
                  />
                }
              />
              {formErrors.mobilePassword && (
                <Text style={[styles.errorText, { color: colors.error }]}>
                  {formErrors.mobilePassword}
                </Text>
              )}
            </View>
          )}

          {/* 用户名注册表单 */}
          {registerType === 'username' && (
            <View style={styles.form}>
              <TextInput
                label="用户名"
                value={username}
                onChangeText={(text) => {
                  setUsername(text);
                  if (formErrors.username) {
                    setFormErrors((prev) => ({ ...prev, username: '' }));
                  }
                }}
                error={!!formErrors.username}
                style={styles.input}
                autoCapitalize="none"
                placeholder="字母/数字，至少3位"
              />
              {formErrors.username && (
                <Text style={[styles.errorText, { color: colors.error }]}>
                  {formErrors.username}
                </Text>
              )}

              <TextInput
                label="密码"
                value={password}
                onChangeText={(text) => {
                  setPassword(text);
                  if (formErrors.password) {
                    setFormErrors((prev) => ({ ...prev, password: '' }));
                  }
                }}
                secureTextEntry={!showPassword}
                error={!!formErrors.password}
                style={styles.input}
                placeholder="至少6位"
                right={
                  <TextInput.Icon
                    icon={showPassword ? 'eye-off' : 'eye'}
                    onPress={() => setShowPassword(!showPassword)}
                  />
                }
              />
              {formErrors.password && (
                <Text style={[styles.errorText, { color: colors.error }]}>
                  {formErrors.password}
                </Text>
              )}

              <TextInput
                label="确认密码"
                value={confirmPassword}
                onChangeText={(text) => {
                  setConfirmPassword(text);
                  if (formErrors.confirmPassword) {
                    setFormErrors((prev) => ({ ...prev, confirmPassword: '' }));
                  }
                }}
                secureTextEntry={!showConfirmPassword}
                error={!!formErrors.confirmPassword}
                style={styles.input}
                right={
                  <TextInput.Icon
                    icon={showConfirmPassword ? 'eye-off' : 'eye'}
                    onPress={() => setShowConfirmPassword(!showConfirmPassword)}
                  />
                }
              />
              {formErrors.confirmPassword && (
                <Text style={[styles.errorText, { color: colors.error }]}>
                  {formErrors.confirmPassword}
                </Text>
              )}

              {/* 图形验证码 */}
              {needCaptcha && (
                <View style={styles.captchaContainer}>
                  <TextInput
                    label="图形验证码"
                    value={captchaCode}
                    onChangeText={setCaptchaCode}
                    error={!!formErrors.captchaCode}
                    style={[styles.input, styles.captchaInput]}
                  />
                  <CaptchaImage
                    captchaId={captchaId}
                    captchaImage={captchaImage}
                    onRefresh={refreshCaptcha}
                  />
                </View>
              )}
              {formErrors.captchaCode && (
                <Text style={[styles.errorText, { color: colors.error }]}>
                  {formErrors.captchaCode}
                </Text>
              )}
            </View>
          )}

          {/* 错误提示 */}
          {registerError && (
            <Text style={[styles.globalError, { color: colors.error }]}>
              {registerError}
            </Text>
          )}

          {/* 用户协议 */}
          <TouchableOpacity
            style={styles.termsContainer}
            onPress={() => setAgreedToTerms(!agreedToTerms)}
          >
            <Checkbox
              status={agreedToTerms ? 'checked' : 'unchecked'}
              onPress={() => setAgreedToTerms(!agreedToTerms)}
            />
            <Text variant="bodySmall" style={styles.termsText}>
              我已阅读并同意
              <Text style={{ color: colors.primary }}>《服务协议》</Text>
              和
              <Text style={{ color: colors.primary }}>《隐私政策》</Text>
            </Text>
          </TouchableOpacity>

          {/* 注册按钮 */}
          <Button
            mode="contained"
            onPress={registerType === 'mobile' ? handleMobileRegister : handleUsernameRegister}
            loading={isLoading}
            disabled={isLoading}
            style={styles.registerButton}
            contentStyle={styles.registerButtonContent}
          >
            注册
          </Button>

          {/* 登录链接 */}
          <View style={styles.loginContainer}>
            <Text style={{ color: colors.text.secondary }}>已有账号?</Text>
            <TouchableOpacity onPress={goToLogin}>
              <Text style={{ color: colors.primary, fontWeight: '600' }}>立即登录</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>

      {/* 协议提示弹窗 */}
      <Portal>
        <Dialog visible={showTermsDialog} onDismiss={() => setShowTermsDialog(false)}>
          <Dialog.Title>提示</Dialog.Title>
          <Dialog.Content>
            <Text>请先阅读并同意《服务协议》和《隐私政策》</Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowTermsDialog(false)}>知道了</Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  keyboardView: {
    flex: 1,
  },
  scrollContent: {
    padding: 24,
  },
  header: {
    alignItems: 'center',
    marginBottom: 32,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 8,
  },
  tabContainer: {
    flexDirection: 'row',
    marginBottom: 24,
  },
  tab: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  activeTab: {
    borderBottomWidth: 2,
  },
  tabText: {
    fontWeight: '500',
  },
  form: {
    marginBottom: 16,
  },
  input: {
    marginBottom: 4,
    backgroundColor: 'transparent',
  },
  captchaContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  captchaInput: {
    flex: 1,
  },
  codeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  codeInput: {
    flex: 1,
  },
  errorText: {
    fontSize: 12,
    marginBottom: 8,
    marginLeft: 4,
  },
  globalError: {
    textAlign: 'center',
    marginBottom: 16,
  },
  termsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  termsText: {
    flex: 1,
    marginLeft: 8,
  },
  registerButton: {
    borderRadius: 8,
    marginBottom: 16,
  },
  registerButtonContent: {
    height: 48,
  },
  loginContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 4,
  },
});
