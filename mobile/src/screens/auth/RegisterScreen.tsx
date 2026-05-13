// 注册页面 - 支持手机号注册和用户名注册

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
  Portal,
  Dialog,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { router } from '@/utils/navigation';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useAuth } from '@/hooks/useAuth';
import { useTheme } from '@/theme';
import { CountdownButton, CaptchaImage, UserAgreement, UserAgreementText } from '@/components/auth';
import { Logo } from '@/components/Logo';
import { AuthManager } from '@/services/auth/AuthManager';
import { authApi } from '@/services/api/auth';
import { validate } from '@/utils/validate';
import { RegisterConfig } from '@/types';

type RegisterType = 'mobile' | 'username';

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
  if (requirements.includes('symbol') && !/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)) {
    errors.push(t('settings.account.specialChar'));
  }

  if (errors.length > 0) {
    return `${t('settings.account.passwordComplexityPrefix')}${errors.join('、')}`;
  }
  return null;
}

export default function RegisterScreen() {
  const { t } = useTranslation();
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

  // 注册/登录配置
  const [registerConfig, setRegisterConfig] = useState<RegisterConfig | null>(null);

  // 加载注册配置和验证码配置
  useEffect(() => {
    loadRegisterConfig();
    loadCaptchaConfig();
  }, []);

  // 加载注册配置
  const loadRegisterConfig = async () => {
    try {
      const config = await AuthManager.getRegisterConfig();
      setRegisterConfig(config);

      // 检查是否启用了注册
      const registerMethods = parseConfigValue(config.register);
      if (registerMethods.length === 0) {
        // 平台未启用注册，跳转回首页
        Alert.alert(t('common.tip'), t('auth.errors.platformRegistrationDisabled'), [
          { text: t('common.confirm'), onPress: () => router.back() },
        ]);
        return;
      }

      // 根据配置设置默认注册方式
      if (registerMethods.includes('username')) {
        setRegisterType('username');
      } else if (registerMethods.includes('mobile')) {
        setRegisterType('mobile');
      }
    } catch (error: any) {
      console.error('获取注册配置失败:', error);
    }
  };

  // 是否显示某注册方式
  const isRegisterMethodEnabled = (method: string): boolean => {
    if (!registerConfig) return true;
    const methods = parseConfigValue(registerConfig.register);
    return methods.length === 0 || methods.includes(method);
  };

  // 是否显示协议
  const showAgreement = (): boolean => {
    if (!registerConfig) return true;
    return registerConfig.agreement_show === 1;
  };

  // 获取密码最小长度
  const getMinPasswordLength = (): number => {
    if (!registerConfig || registerConfig.pwd_len <= 0) return 6;
    return registerConfig.pwd_len;
  };

  // 加载验证码配置
  const loadCaptchaConfig = async () => {
    try {
      const config = await AuthManager.getCaptchaConfig();
      console.log('Captcha config:', config);

      // 如果配置了需要验证码
      if (config && config.shop_reception_register === 1) {
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

  // 手机号注册
  const handleMobileRegister = async () => {
    // 表单验证
    const errors: Record<string, string> = {};

    if (!validate.mobile(mobile)) {
      errors.mobile = t('auth.errors.enterCorrectMobile');
    }
    if (!mobileCode) {
      errors.mobileCode = t('auth.errors.codeRequired');
    }

    const minPwdLen = getMinPasswordLength();
    if (!mobilePassword || mobilePassword.length < minPwdLen) {
      errors.mobilePassword = t('auth.errors.passwordTooShort');
    }

    // 密码复杂度校验
    if (registerConfig?.pwd_complexity) {
      const complexityError = validatePasswordComplexity(mobilePassword, registerConfig.pwd_complexity, t);
      if (complexityError) {
        errors.mobilePassword = complexityError;
      }
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
    setRegisterError('');

    try {
      await authApi.registerWithMobile({
        mobile,
        key: mobileCodeKey,
        code: mobileCode,
        password: mobilePassword,
      });

      // 注册成功，跳转到登录页
      router.replace('Login');
    } catch (error: any) {
      setRegisterError(error.message || t('auth.errors.registerFailed'));
    }
  };

  // 用户名注册
  const handleUsernameRegister = async () => {
    // 表单验证
    const errors: Record<string, string> = {};

    if (!username.trim() || username.length < 3) {
      errors.username = t('auth.errors.usernameMinLength');
    }

    const minPwdLen = getMinPasswordLength();
    if (!password || password.length < minPwdLen) {
      errors.password = t('auth.errors.passwordMinLength', { min: minPwdLen });
    }

    // 密码复杂度校验
    if (registerConfig?.pwd_complexity) {
      const complexityError = validatePasswordComplexity(password, registerConfig.pwd_complexity, t);
      if (complexityError) {
        errors.password = complexityError;
      }
    }

    if (password !== confirmPassword) {
      errors.confirmPassword = t('auth.errors.passwordMismatch');
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
    setRegisterError('');

    try {
      await authApi.registerWithUsername({
        username,
        password,
        captcha_id: captchaId,
        captcha_code: captchaCode,
      });

      // 注册成功，跳转到登录页
      router.replace('Login');
    } catch (error: any) {
      setRegisterError(error.message || t('auth.errors.registerFailed'));
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
          {/* 关闭按钮 */}
          <TouchableOpacity
            style={styles.closeButton}
            onPress={() => router.back()}
          >
            <MaterialIcons name="close" size={24} color={colors.onSurface} />
          </TouchableOpacity>

          {/* 标题 */}
          <View style={styles.header}>
            <Logo variant="icon" asLink={false} size={72} style={styles.logo} />
            <Text variant="headlineLarge" style={[styles.title, { color: colors.onSurface }]}>
              {t('auth.register.title')}
            </Text>
          </View>

          {/* 注册类型切换 - 根据配置显示 */}
          {isRegisterMethodEnabled('mobile') && isRegisterMethodEnabled('username') && (
            <View style={[styles.tabContainer, { backgroundColor: colors.surfaceVariant }]}>
              <TouchableOpacity
                style={[
                  styles.tab,
                  registerType === 'mobile' && [styles.activeTab, { backgroundColor: colors.surface }],
                ]}
                onPress={() => setRegisterType('mobile')}
              >
                <Text
                  variant="labelLarge"
                  style={{ color: registerType === 'mobile' ? colors.onSurface : colors.text.secondary }}
                >
                  {t('auth.register.tabMobile')}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[
                  styles.tab,
                  registerType === 'username' && [styles.activeTab, { backgroundColor: colors.surface }],
                ]}
                onPress={() => setRegisterType('username')}
              >
                <Text
                  variant="labelLarge"
                  style={{ color: registerType === 'username' ? colors.onSurface : colors.text.secondary }}
                >
                  {t('auth.register.tabAccount')}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* 如果只有一种注册方式，显示标题 */}
          {(!isRegisterMethodEnabled('mobile') || !isRegisterMethodEnabled('username')) && (
            <View style={styles.singleRegisterTitle}>
              <Text variant="titleMedium" style={{ color: colors.onSurface }}>
                {isRegisterMethodEnabled('mobile') ? t('auth.register.tabMobile') : t('auth.register.tabAccount')}
              </Text>
            </View>
          )}

          {/* 手机号注册表单 */}
          {(registerType === 'mobile' || !isRegisterMethodEnabled('username')) && isRegisterMethodEnabled('mobile') && (
            <View style={styles.form}>
              <View>
                <TextInput
                  label={t('auth.register.mobilePlaceholder')}
                  value={mobile}
                  onChangeText={(text) => {
                    setMobile(text);
                    if (formErrors.mobile) {
                      setFormErrors((prev) => ({ ...prev, mobile: '' }));
                    }
                  }}
                  placeholder={t('auth.register.mobilePlaceholder')}
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

              <View>
                <TextInput
                  label={t('auth.register.passwordPlaceholder')}
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
                  placeholder={t('auth.register.passwordPlaceholder')}
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
            </View>
          )}

          {/* 用户名注册表单 */}
          {(registerType === 'username' || !isRegisterMethodEnabled('mobile')) && isRegisterMethodEnabled('username') && (
            <View style={styles.form}>
              <View>
                <TextInput
                  label={t('auth.register.usernamePlaceholder')}
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
                  placeholder={t('auth.register.usernamePlaceholder')}
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
                  placeholder={t('auth.register.passwordPlaceholder')}
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

              <View>
                <TextInput
                  label={t('auth.register.passwordPlaceholder')}
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
            </View>
          )}

          {/* 错误提示 */}
          {registerError && (
            <Text style={[styles.globalError, { color: colors.error }]}>
              {registerError}
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

          {/* 注册按钮 */}
          <Button
            mode="contained"
            onPress={registerType === 'mobile' ? handleMobileRegister : handleUsernameRegister}
            loading={isLoading}
            disabled={isLoading}
            style={styles.registerButton}
            contentStyle={styles.registerButtonContent}
          >
            {t('auth.register.submit')}
          </Button>

          {/* 登录链接 */}
          <View style={styles.loginContainer}>
            <Text style={[styles.loginText, { color: colors.text.secondary }]}>{t('auth.register.hasAccount')}</Text>
            <TouchableOpacity onPress={goToLogin}>
              <Text style={[styles.loginText, { color: colors.primary, fontWeight: '600' }]}>
                {t('auth.register.loginNow')}
              </Text>
            </TouchableOpacity>
          </View>
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
    fontSize: 24,
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
  singleRegisterTitle: {
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
  registerButton: {
    borderRadius: 8,
    marginTop: 16,
  },
  registerButtonContent: {
    height: 48,
  },
  loginContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 4,
    marginTop: 16,
  },
  loginText: {
    fontSize: 14,
  },
});
