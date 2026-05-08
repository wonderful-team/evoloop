// 登录页面 - 支持手机号和账号密码登录

import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  Alert,
} from 'react-native';
import {
  Text,
  TextInput,
  Button,
  Divider,
  Portal,
  Dialog,
} from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { router } from '@/utils/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useAuthStore } from '@/stores/authStore';
import { useTheme } from '@/theme';
import { CountdownButton, CaptchaImage, WechatLoginButton, UserAgreement, UserAgreementText } from '@/components/auth';
import { Logo } from '@/components/Logo';
import { AuthManager } from '@/services/auth/AuthManager';
import { api } from '@/services/api/client';
import { validate } from '@/utils/validate';
import { RegisterConfig } from '@/types';

type LoginType = 'mobile' | 'account';

// 解析逗号分隔的配置字符串
function parseConfigValue(value: string | undefined): string[] {
  if (!value) return [];
  return value.split(',').map(s => s.trim()).filter(Boolean);
}

export default function LoginScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const {
    loginWithMobile,
    loginWithAccount,
    sendMobileCode,
    isLoading,
    error,
  } = useAuth();

  const { login } = useAuthStore();

  // 注册/登录配置
  const [registerConfig, setRegisterConfig] = useState<RegisterConfig | null>(null);

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

  // 加载注册/登录配置
  useEffect(() => {
    loadRegisterConfig();
  }, []);

  // 加载验证码配置
  useEffect(() => {
    loadCaptchaConfig();
  }, []);

  // 加载注册配置
  const loadRegisterConfig = async () => {
    try {
      const config = await AuthManager.getRegisterConfig();
      setRegisterConfig(config);

      // 根据配置设置默认登录方式
      const loginMethods = parseConfigValue(config.login);
      if (loginMethods.length > 0) {
        // 优先使用手机号登录
        if (loginMethods.includes('mobile')) {
          setLoginType('mobile');
        } else if (loginMethods.includes('username')) {
          setLoginType('account');
        }
      }
    } catch (error: any) {
      console.error('获取注册配置失败:', error);
    }
  };

  // 是否显示某登录方式
  const isLoginMethodEnabled = (method: string): boolean => {
    if (!registerConfig) return true; // 默认全部显示
    const methods = parseConfigValue(registerConfig.login);
    return methods.length === 0 || methods.includes(method);
  };

  // 是否显示第三方登录
  const showThirdPartyLogin = (): boolean => {
    if (!registerConfig) return true;
    return registerConfig.third_party === 1;
  };

  // 是否显示协议
  const showAgreement = (): boolean => {
    if (!registerConfig) return true;
    return registerConfig.agreement_show === 1;
  };

  // 登录页面描述
  const getLoginDesc = (): string => {
    if (registerConfig?.wap_desc) return registerConfig.wap_desc;
    return t('auth.login.subtitle');
  };

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
        throw new Error(t('auth.errors.getCaptchaFailed'));
      }

      if (!captcha.img) {
        console.error('验证码数据不完整:', captcha);
        throw new Error(t('auth.errors.captchaDataIncomplete'));
      }

      setCaptchaId(captcha.id);
      setCaptchaImage(captcha.img);
    } catch (error: any) {
      console.error('获取图形验证码失败:', error);
      // 如果验证码服务不可用，禁用验证码功能
      setNeedCaptcha(false);
      setFormErrors({
        captchaCode: error.message || t('auth.errors.captchaUnavailable')
      });
      throw error;
    }
  };

  // 发送手机验证码
  const handleSendMobileCode = async () => {
    // 验证手机号
    if (!validate.mobile(mobile)) {
      setFormErrors({ mobile: t('auth.errors.enterCorrectMobile') });
      Alert.alert(t('common.tip'), t('auth.errors.enterCorrectMobile'));
      return false;
    }

    // 如果需要图形验证码
    if (needCaptcha && !captchaCode) {
      setFormErrors({ captchaCode: t('auth.errors.enterCaptcha') });
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
        mobile: error.message || t('auth.errors.sendCodeFailed'),
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
      errors.mobile = t('auth.errors.enterCorrectMobile');
    }
    if (!mobileCode) {
      errors.mobileCode = t('auth.errors.codeRequired');
    }
    if (needCaptcha && !captchaCode) {
      errors.captchaCode = t('auth.errors.enterCaptcha');
    }
    if (showAgreement() && !agreedToTerms) {
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
      errors.username = t('auth.errors.enterUsername');
    }
    if (!password) {
      errors.password = t('auth.errors.enterPassword');
    }
    if (needCaptcha && !captchaCode) {
      errors.captchaCode = t('auth.errors.enterCaptcha');
    }
    if (showAgreement() && !agreedToTerms) {
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
      captcha_id: captchaId,
      captcha_code: captchaCode,
    });
  };

  // 微信登录
  const handleWechatLogin = async () => {
    if (showAgreement() && !agreedToTerms) {
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
        router.push('BindMobile', {
          wx_openid: result.wx_openid,
          wx_unionid: result.wx_unionid,
          nickname: result.nickname,
          avatar: result.avatar,
        });
      } else if (result.token) {
        // 登录成功，获取用户信息
        api.setAuthToken(result.token);
        const userInfo = await AuthManager.getMemberInfo();
        await login(result.token, userInfo);
        router.replace('Main');
      }
    } catch (error: any) {
      console.error('微信登录失败:', error);
      // 显示错误提示
      setFormErrors({
        global: error.message || t('auth.errors.wechatLoginFailed')
      });
    }
  };

  // 跳转到注册
  const goToRegister = () => {
    router.push('Register');
  };

  // 跳转到找回密码
  const goToForgotPassword = () => {
    router.push('ForgotPassword');
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
          {/* 关闭按钮 */}
          <TouchableOpacity
            style={styles.closeButton}
            onPress={() => {
              const canGoBack = router.back();
              if (!canGoBack) {
                router.replace('Main');
              }
            }}
          >
            <MaterialIcons name="close" size={24} color={colors.onSurface} />
          </TouchableOpacity>

          {/* 标题 */}
          <View style={styles.header}>
            <Logo variant="icon" asLink={false} size={72} style={styles.logo} />
            <Text variant="headlineLarge" style={[styles.title, { color: colors.onSurface }]}>
              {t('auth.login.welcomeBack')}
            </Text>
          </View>

          {/* 登录类型切换 - 根据配置显示 */}
          {isLoginMethodEnabled('mobile') && isLoginMethodEnabled('username') && (
            <View style={[styles.tabContainer, { backgroundColor: colors.surfaceVariant }]}>
              <TouchableOpacity
                style={[
                  styles.tab,
                  loginType === 'mobile' && [styles.activeTab, { backgroundColor: colors.surface }],
                ]}
                onPress={() => setLoginType('mobile')}
              >
                <Text
                  variant="labelLarge"
                  style={{ color: loginType === 'mobile' ? colors.onSurface : colors.text.secondary }}
                >
                  {t('auth.login.mobileLogin')}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[
                  styles.tab,
                  loginType === 'account' && [styles.activeTab, { backgroundColor: colors.surface }],
                ]}
                onPress={() => setLoginType('account')}
              >
                <Text
                  variant="labelLarge"
                  style={{ color: loginType === 'account' ? colors.onSurface : colors.text.secondary }}
                >
                  {t('auth.login.tabAccount')}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* 如果只有一种登录方式，显示标题 */}
          {(!isLoginMethodEnabled('mobile') || !isLoginMethodEnabled('username')) && (
            <View style={styles.singleLoginTitle}>
              <Text variant="titleMedium" style={{ color: colors.onSurface }}>
                {isLoginMethodEnabled('mobile') ? t('auth.login.mobileLogin') : t('auth.login.accountLogin')}
              </Text>
            </View>
          )}

          {/* 手机号登录表单 */}
          {(loginType === 'mobile' || !isLoginMethodEnabled('username')) && isLoginMethodEnabled('mobile') && (
            <View style={styles.form}>
              <View>
                <TextInput
                  label={t('auth.login.mobilePlaceholder')}
                  value={mobile}
                  onChangeText={(text) => {
                    setMobile(text);
                    if (formErrors.mobile) {
                      setFormErrors((prev) => ({ ...prev, mobile: '' }));
                    }
                  }}
                  placeholder={t('auth.login.mobilePlaceholder')}
                  keyboardType="phone-pad"
                  maxLength={11}
                  error={!!formErrors.mobile}
                  style={styles.input}
                />
                {formErrors.mobile && (
                  <Text style={[styles.errorText, { color: colors.error }]}>
                    {formErrors.mobile}
                  </Text>
                )}
              </View>

              {/* 图形验证码 */}
              {needCaptcha && (
                <View>
                  <View style={styles.captchaContainer}>
                    <TextInput
                      label={t('auth.login.captchaLabel')}
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
                  {formErrors.captchaCode && (
                    <Text style={[styles.errorText, { color: colors.error }]}>
                      {formErrors.captchaCode}
                    </Text>
                  )}
                </View>
              )}

              <View>
                <View style={styles.codeContainer}>
                  <TextInput
                    label={t('auth.login.smsCodeLabel')}
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
            </View>
          )}

          {/* 账号密码登录表单 */}
          {(loginType === 'account' || !isLoginMethodEnabled('mobile')) && isLoginMethodEnabled('username') && (
            <View style={styles.form}>
              <View>
                <TextInput
                  label={t('auth.login.usernameLabel')}
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
              </View>

              <View>
                <TextInput
                  label={t('auth.login.passwordLabel')}
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
              </View>

              {/* 图形验证码 */}
              {needCaptcha && (
                <View>
                  <View style={styles.captchaContainer}>
                    <TextInput
                      label={t('auth.login.captchaLabel')}
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
                  {formErrors.captchaCode && (
                    <Text style={[styles.errorText, { color: colors.error }]}>
                      {formErrors.captchaCode}
                    </Text>
                  )}
                </View>
              )}

              <TouchableOpacity onPress={goToForgotPassword} style={styles.forgotPassword}>
                <Text style={[styles.forgotPasswordText, { color: colors.text.secondary }]}>
                  {t('auth.login.forgotPassword')}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* 错误提示 */}
          {(error || formErrors.global) && (
            <Text style={[styles.globalError, { color: colors.error }]}>
              {error?.message || formErrors.global}
            </Text>
          )}

          {/* 用户协议 - 根据配置显示 */}
          {showAgreement() && (
            <UserAgreement
              agreed={agreedToTerms}
              onToggle={() => setAgreedToTerms(!agreedToTerms)}
              style={styles.termsContainer}
            />
          )}

          {/* 登录按钮 */}
          <Button
            mode="contained"
            onPress={loginType === 'mobile' ? handleMobileLogin : handleAccountLogin}
            loading={isLoading}
            disabled={isLoading}
            style={styles.loginButton}
            contentStyle={styles.loginButtonContent}
          >
            {t('auth.login.submit')}
          </Button>

          {/* 注册链接 - 根据配置显示 */}
          {registerConfig?.register !== '' && (
            <View style={styles.registerContainer}>
              <Text style={[styles.registerText, { color: colors.text.secondary }]}>
                {t('auth.login.noAccount')}
              </Text>
              <TouchableOpacity onPress={goToRegister}>
                <Text style={[styles.registerText, { color: colors.primary, fontWeight: '600' }]}>
                  {t('auth.login.registerNow')}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* 第三方登录 - 根据配置显示 */}
          {showThirdPartyLogin() && (
            <>
              <Divider style={styles.divider} />
              <WechatLoginButton
                onPress={handleWechatLogin}
                disabled={isLoading || (showAgreement() && !agreedToTerms)}
                loading={isLoading}
              />
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>

      {/* 协议提示弹窗 */}
      <Portal>
        <Dialog visible={showTermsDialog} onDismiss={() => setShowTermsDialog(false)}>
          <Dialog.Title>{t('common.tip')}</Dialog.Title>
          <Dialog.Content>
            <UserAgreementText />
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowTermsDialog(false)}>{t('common.gotIt')}</Button>
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
  closeButton: {
    alignSelf: 'flex-end',
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 20,
    marginTop: 8,
    marginRight: -8,
  },
  header: {
    alignItems: 'center',
    marginTop: 16,
    marginBottom: 32,
    gap: 12,
  },
  logo: {
    marginBottom: 4,
  },
  title: {
    fontWeight: 'bold',
    fontSize: 32,
    letterSpacing: -0.5,
  },
  tabContainer: {
    flexDirection: 'row',
    borderRadius: 8,
    padding: 4,
    marginBottom: 24,
  },
  tab: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 6,
  },
  activeTab: {},
  singleLoginTitle: {
    alignItems: 'center',
    marginBottom: 24,
  },
  form: {
    gap: 16,
  },
  input: {
    backgroundColor: 'transparent',
  },
  captchaContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  captchaInput: {
    flex: 1,
  },
  codeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  codeInput: {
    flex: 1,
  },
  errorText: {
    fontSize: 12,
    marginTop: 4,
    marginLeft: 4,
  },
  forgotPassword: {
    alignSelf: 'flex-end',
    marginTop: 4,
  },
  forgotPasswordText: {
    fontSize: 13,
  },
  globalError: {
    textAlign: 'center',
    marginTop: 8,
    fontSize: 13,
  },
  termsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 16,
  },
  termsText: {
    flex: 1,
    marginLeft: 8,
  },
  loginButton: {
    borderRadius: 8,
    marginTop: 16,
  },
  loginButtonContent: {
    height: 48,
  },
  registerContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 4,
    marginTop: 16,
  },
  registerText: {
    fontSize: 14,
  },
  divider: {
    marginVertical: 24,
  },
});
