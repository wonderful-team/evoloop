// 找回密码页面 - 三步流程：验证手机号 -> 输入验证码 -> 设置新密码

import React, { useState, useEffect } from 'react';
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
  Portal,
  Dialog,
  ProgressBar,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { router } from '@/utils/navigation';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { CountdownButton, CaptchaImage } from '@/components/auth';
import { AuthManager } from '@/services/auth/AuthManager';
import { authApi } from '@/services/api/auth';
import { validate } from '@/utils/validate';
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
  if (requirements.includes('symbol') && !/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)) {
    errors.push(t('settings.account.specialChar'));
  }

  if (errors.length > 0) {
    return `${t('settings.account.passwordComplexityPrefix')}${errors.join('、')}`;
  }
  return null;
}

type Step = 0 | 1 | 2; // 0: 验证手机号, 1: 输入验证码, 2: 设置新密码

export default function ForgotPasswordScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();

  // 当前步骤
  const [currentStep, setCurrentStep] = useState<Step>(0);
  const [isLoading, setIsLoading] = useState(false);

  // 手机号
  const [mobile, setMobile] = useState('');

  // 验证码
  const [code, setCode] = useState('');
  const [codeKey, setCodeKey] = useState('');

  // 新密码
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  // 图形验证码（始终显示，不读配置 — 与 mobile_uniapp 一致）
  const [captchaId, setCaptchaId] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');

  // 表单错误
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [errorMessage, setErrorMessage] = useState('');

  // 成功弹窗
  const [showSuccessDialog, setShowSuccessDialog] = useState(false);

  // 注册配置
  const [registerConfig, setRegisterConfig] = useState<RegisterConfig | null>(null);

  // 加载注册配置
  useEffect(() => {
    loadRegisterConfig();
  }, []);

  // 加载注册配置（用于密码校验规则）
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

  // 加载图形验证码（找回密码强制显示，不读配置 — 与 mobile_uniapp 一致）
  useEffect(() => {
    refreshCaptcha();
  }, []);

  // 刷新图形验证码
  const refreshCaptcha = async () => {
    try {
      setFormErrors({});

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
      setFormErrors({
        captchaCode: error.message || t('auth.errors.captchaUnavailable')
      });
    }
  };

  // 步骤标题和描述
  const stepInfo = [
    { title: t('auth.forgotPassword.step0'), description: t('auth.forgotPassword.mobilePlaceholder') },
    { title: t('auth.forgotPassword.step1'), description: `${t('auth.forgotPassword.sentTo')} ${mobile}` },
    { title: t('auth.forgotPassword.step2'), description: t('auth.forgotPassword.step2') },
  ];

  // 发送验证码
  const handleSendCode = async () => {
    if (!validate.mobile(mobile)) {
      setFormErrors({ mobile: t('auth.errors.enterCorrectMobile') });
      return false;
    }

    if (!captchaCode) {
      setFormErrors({ captchaCode: t('auth.errors.enterCaptcha') });
      return false;
    }

    setIsLoading(true);
    try {
      const result = await authApi.sendFindPasswordCode(
        mobile,
        captchaCode,
        captchaId
      );
      if (result) {
        setCodeKey(result.key);
        setFormErrors({});
        setCurrentStep(1);
        return true;
      }
    } catch (error: any) {
      setFormErrors({
        mobile: error.message || t('auth.errors.sendCodeFailed'),
      });
      refreshCaptcha();
    } finally {
      setIsLoading(false);
    }
    return false;
  };

  // 验证验证码
  const handleVerifyCode = async () => {
    if (!code) {
      setFormErrors({ code: t('auth.errors.codeRequired') });
      return;
    }

    setFormErrors({});
    setCurrentStep(2);
  };

  // 重置密码
  const handleResetPassword = async () => {
    const errors: Record<string, string> = {};

    const minPwdLen = getMinPasswordLength();
    if (!newPassword || newPassword.length < minPwdLen) {
      errors.newPassword = t('auth.errors.passwordMinLength', { min: minPwdLen });
    }

    if (registerConfig?.pwd_complexity) {
      const complexityError = validatePasswordComplexity(newPassword, registerConfig.pwd_complexity, t);
      if (complexityError) {
        errors.newPassword = complexityError;
      }
    }

    if (newPassword !== confirmPassword) {
      errors.confirmPassword = t('auth.errors.passwordMismatch');
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    setFormErrors({});
    setErrorMessage('');
    setIsLoading(true);

    try {
      await authApi.resetPassword({
        mobile,
        key: codeKey,
        code,
        password: newPassword,
      });

      setShowSuccessDialog(true);
    } catch (error: any) {
      setErrorMessage(error.message || t('auth.errors.resetFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  // 返回上一步或关闭
  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep((prev) => (prev - 1) as Step);
    } else {
      router.back();
    }
  };

  // 重置完成，返回登录
  const handleComplete = () => {
    setShowSuccessDialog(false);
    router.replace('Login');
  };

  // 渲染步骤指示器
  const renderStepIndicator = () => (
    <View style={styles.stepIndicator}>
      <View style={styles.stepRow}>
        {[0, 1, 2].map((step) => (
          <View
            key={step}
            style={[
              styles.stepDot,
              {
                backgroundColor:
                  step <= currentStep ? colors.primary : colors.surfaceVariant,
              },
            ]}
          >
            <Text style={{ color: step <= currentStep ? '#fff' : colors.onSurfaceVariant }}>
              {step + 1}
            </Text>
          </View>
        ))}
      </View>
      <ProgressBar
        progress={(currentStep + 1) / 3}
        color={colors.primary}
        style={styles.progressBar}
      />
    </View>
  );

  // 渲染步骤 0: 验证手机号
  const renderStep0 = () => (
    <View style={styles.form}>
      <View>
        <TextInput
          label={t('auth.forgotPassword.mobilePlaceholder')}
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
          style={styles.input}
        />
        {formErrors.mobile && (
          <Text style={[styles.errorText, { color: colors.error }]}>
            {formErrors.mobile}
          </Text>
        )}
      </View>

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

      <Button
        mode="contained"
        onPress={handleSendCode}
        loading={isLoading}
        disabled={isLoading}
        style={styles.actionButton}
        contentStyle={styles.actionButtonContent}
      >
        {t('auth.login.getCode')}
      </Button>
    </View>
  );

  // 渲染步骤 1: 输入验证码
  const renderStep1 = () => (
    <View style={styles.form}>
      <View style={styles.codeInfoContainer}>
        <MaterialIcons name="sms" size={48} color={colors.primary} />
        <Text variant="bodyLarge" style={styles.codeInfoText}>
          {t('auth.forgotPassword.sentTo')}
        </Text>
        <Text variant="titleMedium" style={{ color: colors.primary }}>
          {mobile}
        </Text>
      </View>

      <View>
        <TextInput
          label={t('auth.login.smsCodeLabel')}
          value={code}
          onChangeText={(text) => {
            setCode(text);
            if (formErrors.code) {
              setFormErrors((prev) => ({ ...prev, code: '' }));
            }
          }}
          keyboardType="number-pad"
          maxLength={6}
          error={!!formErrors.code}
          style={styles.input}
        />
        {formErrors.code && (
          <Text style={[styles.errorText, { color: colors.error }]}>
            {formErrors.code}
          </Text>
        )}
      </View>

      <View style={styles.resendContainer}>
        <Text style={{ color: colors.text.secondary }}>{t('auth.forgotPassword.noReceived')}</Text>
        <CountdownButton
          onPress={handleSendCode}
          disabled={!validate.mobile(mobile)}
          label={t('auth.forgotPassword.resend')}
        />
      </View>

      <Button
        mode="contained"
        onPress={handleVerifyCode}
        style={styles.actionButton}
        contentStyle={styles.actionButtonContent}
      >
        {t('auth.forgotPassword.next')}
      </Button>
    </View>
  );

  // 渲染步骤 2: 设置新密码
  const renderStep2 = () => (
    <View style={styles.form}>
      <View>
        <TextInput
          label={t('auth.login.passwordLabel')}
          value={newPassword}
          onChangeText={(text) => {
            setNewPassword(text);
            if (formErrors.newPassword) {
              setFormErrors((prev) => ({ ...prev, newPassword: '' }));
            }
          }}
          secureTextEntry={!showNewPassword}
          error={!!formErrors.newPassword}
          style={styles.input}
          placeholder={t('auth.register.passwordPlaceholder')}
          right={
            <TextInput.Icon
              icon={showNewPassword ? 'eye-off' : 'eye'}
              onPress={() => setShowNewPassword(!showNewPassword)}
            />
          }
        />
        {formErrors.newPassword && (
          <Text style={[styles.errorText, { color: colors.error }]}>
            {formErrors.newPassword}
          </Text>
        )}
      </View>

      <View>
        <TextInput
          label={t('auth.login.passwordLabel')}
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

      {errorMessage && (
        <Text style={[styles.globalError, { color: colors.error }]}>
          {errorMessage}
        </Text>
      )}

      <Button
        mode="contained"
        onPress={handleResetPassword}
        loading={isLoading}
        disabled={isLoading}
        style={styles.actionButton}
        contentStyle={styles.actionButtonContent}
      >
        {t('auth.forgotPassword.submit')}
      </Button>
    </View>
  );

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
            onPress={handleBack}
          >
            <MaterialIcons name="close" size={24} color={colors.onSurface} />
          </TouchableOpacity>

          {/* 标题 */}
          <View style={styles.header}>
            <Text variant="headlineLarge" style={[styles.title, { color: colors.onSurface }]}>
              {stepInfo[currentStep].title}
            </Text>
            <Text variant="bodyLarge" style={{ color: colors.text.secondary }}>
              {stepInfo[currentStep].description}
            </Text>
          </View>

          {/* 步骤指示器 */}
          {renderStepIndicator()}

          {/* 步骤内容 */}
          {currentStep === 0 && renderStep0()}
          {currentStep === 1 && renderStep1()}
          {currentStep === 2 && renderStep2()}
        </ScrollView>
      </KeyboardAvoidingView>

      {/* 成功弹窗 */}
      <Portal>
        <Dialog visible={showSuccessDialog} onDismiss={handleComplete}>
          <Dialog.Icon icon="check-circle" size={48} color={colors.primary} />
          <Dialog.Title style={styles.dialogTitle}>{t('auth.forgotPassword.resetSuccess')}</Dialog.Title>
          <Dialog.Content>
            <Text style={styles.dialogContent}>
              {t('auth.forgotPassword.resetSuccessDesc')}
            </Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={handleComplete} mode="contained">
              {t('auth.forgotPassword.goLogin')}
            </Button>
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
    marginBottom: 24,
    gap: 8,
  },
  title: {
    fontWeight: 'bold',
    fontSize: 24,
    letterSpacing: -0.5,
  },
  stepIndicator: {
    marginBottom: 24,
  },
  stepRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
    paddingHorizontal: 16,
  },
  stepDot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  progressBar: {
    height: 4,
    borderRadius: 2,
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
  errorText: {
    fontSize: 12,
    marginTop: 4,
    marginLeft: 4,
  },
  globalError: {
    textAlign: 'center',
    fontSize: 13,
  },
  actionButton: {
    borderRadius: 8,
    marginTop: 8,
  },
  actionButtonContent: {
    height: 48,
  },
  codeInfoContainer: {
    alignItems: 'center',
    marginBottom: 8,
    padding: 16,
  },
  codeInfoText: {
    marginTop: 16,
    marginBottom: 4,
  },
  resendContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  dialogTitle: {
    textAlign: 'center',
  },
  dialogContent: {
    textAlign: 'center',
    color: '#757575',
  },
});
