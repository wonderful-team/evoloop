// 找回密码页面 - 三步流程：验证手机号 -> 输入验证码 -> 设置新密码

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
  Portal,
  Dialog,
  ProgressBar,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useRouter } from 'expo-router';
import { MaterialIcons } from '@expo/vector-icons';
import { useTheme } from '@/theme';
import { CountdownButton, CaptchaImage } from '@/components/auth';
import { AuthManager } from '@/services/auth/AuthManager';
import { api } from '@/services/api/client';
import { MEMBER_API } from '@/constants/api';
import { validate } from '@/utils/validate';

type Step = 0 | 1 | 2; // 0: 验证手机号, 1: 输入验证码, 2: 设置新密码

export default function ForgotPasswordScreen() {
  const { t } = useTranslation();
  const router = useRouter();
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

  // 图形验证码
  const [captchaId, setCaptchaId] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');
  const [needCaptcha, setNeedCaptcha] = useState(false);

  // 表单错误
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [errorMessage, setErrorMessage] = useState('');

  // 成功弹窗
  const [showSuccessDialog, setShowSuccessDialog] = useState(false);

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

  // 步骤标题和描述
  const stepInfo = [
    { title: '验证手机号', description: '请输入您注册时使用的手机号' },
    { title: '输入验证码', description: `验证码已发送至 ${mobile}` },
    { title: '设置新密码', description: '请设置您的新密码' },
  ];

  // 发送验证码
  const handleSendCode = async () => {
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

    setIsLoading(true);
    try {
      const result = await AuthManager.sendMobileCode(mobile, captchaId, captchaCode, 'reset');
      if (result) {
        setCodeKey(result.key);
        setFormErrors({});
        setCurrentStep(1);
        return true;
      }
    } catch (error: any) {
      setFormErrors({
        mobile: error.message || '发送验证码失败',
      });
      if (needCaptcha) {
        refreshCaptcha();
      }
    } finally {
      setIsLoading(false);
    }
    return false;
  };

  // 验证验证码
  const handleVerifyCode = async () => {
    if (!code) {
      setFormErrors({ code: '请输入验证码' });
      return;
    }

    setFormErrors({});
    setCurrentStep(2);
  };

  // 重置密码
  const handleResetPassword = async () => {
    // 表单验证
    const errors: Record<string, string> = {};

    if (!newPassword || newPassword.length < 6) {
      errors.newPassword = '密码至少6位';
    }
    if (newPassword !== confirmPassword) {
      errors.confirmPassword = '两次密码不一致';
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    setFormErrors({});
    setErrorMessage('');
    setIsLoading(true);

    try {
      // 调用重置密码 API
      const response = await api.post('/api/member/resetPassword', {
        mobile,
        key: codeKey,
        code,
        new_password: newPassword,
      });

      if (response.data?.code === 0) {
        setShowSuccessDialog(true);
      } else {
        setErrorMessage(response.data?.message || '重置密码失败');
      }
    } catch (error: any) {
      setErrorMessage(error.message || '重置密码失败，请重试');
    } finally {
      setIsLoading(false);
    }
  };

  // 返回上一步
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
    router.replace('/(auth)/login');
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
            <Text style={{ color: step <= currentStep ? '#fff' : colors.text.secondary }}>
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

      <Button
        mode="contained"
        onPress={handleSendCode}
        loading={isLoading}
        disabled={isLoading}
        style={styles.actionButton}
        contentStyle={styles.actionButtonContent}
      >
        获取验证码
      </Button>
    </View>
  );

  // 渲染步骤 1: 输入验证码
  const renderStep1 = () => (
    <View style={styles.form}>
      <View style={styles.codeInfoContainer}>
        <MaterialIcons name="sms" size={48} color={colors.primary} />
        <Text variant="bodyLarge" style={styles.codeInfoText}>
          验证码已发送至
        </Text>
        <Text variant="titleMedium" style={{ color: colors.primary }}>
          {mobile}
        </Text>
      </View>

      <TextInput
        label="验证码"
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

      <View style={styles.resendContainer}>
        <Text style={{ color: colors.text.secondary }}>没有收到?</Text>
        <CountdownButton
          onPress={handleSendCode}
          disabled={!validate.mobile(mobile)}
          label="重新发送"
        />
      </View>

      <Button
        mode="contained"
        onPress={handleVerifyCode}
        style={styles.actionButton}
        contentStyle={styles.actionButtonContent}
      >
        下一步
      </Button>
    </View>
  );

  // 渲染步骤 2: 设置新密码
  const renderStep2 = () => (
    <View style={styles.form}>
      <TextInput
        label="新密码"
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
        placeholder="至少6位"
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
        重置密码
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
          {/* 返回按钮 */}
          <TouchableOpacity onPress={handleBack} style={styles.backButton}>
            <MaterialIcons name="arrow-back" size={24} color={colors.text.primary} />
          </TouchableOpacity>

          {/* 标题 */}
          <View style={styles.header}>
            <Text variant="headlineLarge" style={[styles.title, { color: colors.primary }]}>
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
          <Dialog.Icon icon="check-circle" size={48} color={colors.status.success} />
          <Dialog.Title style={styles.dialogTitle}>重置成功</Dialog.Title>
          <Dialog.Content>
            <Text style={styles.dialogContent}>
              您的密码已重置成功，请使用新密码登录。
            </Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={handleComplete} mode="contained">
              去登录
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
  backButton: {
    marginBottom: 16,
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: -8,
  },
  header: {
    marginBottom: 32,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 8,
  },
  stepIndicator: {
    marginBottom: 32,
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
    marginBottom: 16,
  },
  captchaInput: {
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
  actionButton: {
    borderRadius: 8,
    marginTop: 16,
  },
  actionButtonContent: {
    height: 48,
  },
  codeInfoContainer: {
    alignItems: 'center',
    marginBottom: 24,
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
    marginTop: 8,
    marginBottom: 16,
  },
  dialogTitle: {
    textAlign: 'center',
  },
  dialogContent: {
    textAlign: 'center',
    color: '#666',
  },
});
