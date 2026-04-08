// 登录页面 - 支持手机号和账号密码登录

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
  Divider,
  Checkbox,
  Portal,
  Dialog,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useRouter } from 'expo-router';
import { useAuth } from '@/hooks/useAuth';
import { useAuthStore } from '@/stores/authStore';
import { useTheme } from '@/theme';
import { CountdownButton, CaptchaImage, WechatLoginButton } from '@/components/auth';
import { AuthManager } from '@/services/auth/AuthManager';
import { api } from '@/services/api/client';
import { validate } from '@/utils/validate';

type LoginType = 'mobile' | 'account';

export default function LoginScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { colors } = useTheme();
  const {
    loginWithMobile,
    loginWithAccount,
    sendMobileCode,
    isLoading,
    error,
  } = useAuth();
  
  const { login } = useAuthStore();

  // 登录类型
  const [loginType, setLoginType] = useState<LoginType>('mobile');

  // 手机号登录表单
  const [mobile, setMobile] = useState('');
  const [mobileCode, setMobileCode] = useState('');
  const [mobileCodeKey, setMobileCodeKey] = useState('');

  // 账号密码登录表单
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

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
      throw error;
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

  // 手机号登录
  const handleMobileLogin = async () => {
    // 表单验证
    const errors: Record<string, string> = {};

    if (!validate.mobile(mobile)) {
      errors.mobile = '请输入正确的手机号';
    }
    if (!mobileCode) {
      errors.mobileCode = '请输入验证码';
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

    await loginWithMobile({
      mobile,
      key: mobileCodeKey,
      code: mobileCode,
    });
  };

  // 账号密码登录
  const handleAccountLogin = async () => {
    // 表单验证
    const errors: Record<string, string> = {};

    if (!username.trim()) {
      errors.username = '请输入账号';
    }
    if (!password) {
      errors.password = '请输入密码';
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

    await loginWithAccount({
      username,
      password,
      captcha_code: captchaCode,
    });
  };

  // 微信登录
  const handleWechatLogin = async () => {
    if (!agreedToTerms) {
      setShowTermsDialog(true);
      return;
    }

    try {
      // 动态导入微信登录模块（避免在 Expo Go 中崩溃）
      const { WechatAuth } = await import('@/services/auth/WechatAuth');
      
      // 调用微信登录
      const result = await WechatAuth.login();
      
      if (result.need_bind_mobile) {
        // 需要绑定手机号
        router.push({
          pathname: '/(auth)/bind-mobile',
          params: {
            wx_openid: result.wx_openid,
            wx_unionid: result.wx_unionid,
            nickname: result.nickname,
            avatar: result.avatar,
          }
        });
      } else if (result.token) {
        // 登录成功，获取用户信息
        api.setAuthToken(result.token);
        const userInfo = await AuthManager.getMemberInfo();
        login(result.token, userInfo);
        router.replace('/(main)');
      }
    } catch (error: any) {
      console.error('微信登录失败:', error);
      // 显示错误提示
      setFormErrors({
        global: error.message || '微信登录失败，请重试'
      });
    }
  };

  // 跳转到注册
  const goToRegister = () => {
    router.push('/(auth)/register');
  };

  // 跳转到找回密码
  const goToForgotPassword = () => {
    router.push('/(auth)/forgot-password');
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
              EvoLoop
            </Text>
            <Text variant="bodyLarge" style={{ color: colors.text.secondary }}>
              {t('auth.login.subtitle')}
            </Text>
          </View>

          {/* 登录类型切换 */}
          <View style={styles.tabContainer}>
            <TouchableOpacity
              style={[
                styles.tab,
                loginType === 'mobile' && [styles.activeTab, { borderBottomColor: colors.primary }],
              ]}
              onPress={() => setLoginType('mobile')}
            >
              <Text
                variant="titleMedium"
                style={[
                  styles.tabText,
                  { color: loginType === 'mobile' ? colors.primary : colors.text.secondary },
                ]}
              >
                手机号登录
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[
                styles.tab,
                loginType === 'account' && [styles.activeTab, { borderBottomColor: colors.primary }],
              ]}
              onPress={() => setLoginType('account')}
            >
              <Text
                variant="titleMedium"
                style={[
                  styles.tabText,
                  { color: loginType === 'account' ? colors.primary : colors.text.secondary },
                ]}
              >
                账号密码
              </Text>
            </TouchableOpacity>
          </View>

          {/* 手机号登录表单 */}
          {loginType === 'mobile' && (
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
            </View>
          )}

          {/* 账号密码登录表单 */}
          {loginType === 'account' && (
            <View style={styles.form}>
              <TextInput
                label="账号/手机号/邮箱"
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

              <TouchableOpacity onPress={goToForgotPassword} style={styles.forgotPassword}>
                <Text style={{ color: colors.primary }}>忘记密码?</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* 错误提示 */}
          {(error || formErrors.global) && (
            <Text style={[styles.globalError, { color: colors.error }]}>
              {error?.message || formErrors.global}
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

          {/* 登录按钮 */}
          <Button
            mode="contained"
            onPress={loginType === 'mobile' ? handleMobileLogin : handleAccountLogin}
            loading={isLoading}
            disabled={isLoading}
            style={styles.loginButton}
            contentStyle={styles.loginButtonContent}
          >
            登录
          </Button>

          {/* 注册链接 */}
          <View style={styles.registerContainer}>
            <Text style={{ color: colors.text.secondary }}>还没有账号?</Text>
            <TouchableOpacity onPress={goToRegister}>
              <Text style={{ color: colors.primary, fontWeight: '600' }}>立即注册</Text>
            </TouchableOpacity>
          </View>

          {/* 微信登录 */}
          <Divider style={styles.divider} />
          <WechatLoginButton
            onPress={handleWechatLogin}
            disabled={isLoading || !agreedToTerms}
            loading={isLoading}
          />
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
  forgotPassword: {
    alignSelf: 'flex-end',
    marginTop: 4,
    marginBottom: 16,
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
  loginButton: {
    borderRadius: 8,
    marginBottom: 16,
  },
  loginButtonContent: {
    height: 48,
  },
  registerContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 4,
    marginBottom: 24,
  },
  divider: {
    marginBottom: 24,
  },
});
