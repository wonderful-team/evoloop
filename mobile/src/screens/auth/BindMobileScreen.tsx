// 微信登录后绑定手机号页面
// 参照 mobile_uniapp 的 ns-login.vue 实现

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
  Avatar,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRoute } from '@react-navigation/native';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
import { AuthManager } from '@/services/auth/AuthManager';
import { api } from '@/services/api/client';
import { useAuthStore } from '@/stores/authStore';
import { validate } from '@/utils/validate';
import { CountdownButton, CaptchaImage } from '@/components/auth';
import { router } from '@/utils/navigation';

export default function BindMobileScreen() {
  const route = useRoute<any>();
  const { colors } = useTheme();
  const { login } = useAuthStore();
  const { t } = useTranslation();

  // 微信授权信息（从路由参数传入）
  const wxOpenid = route.params?.wx_openid || '';
  const wxUnionid = route.params?.wx_unionid || '';
  const nickname = route.params?.nickname || '';
  const avatar = route.params?.avatar || '';

  // 表单状态
  const [mobile, setMobile] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');
  const [dynaCode, setDynaCode] = useState('');
  const [dynaCodeKey, setDynaCodeKey] = useState('');

  // 图形验证码（始终显示，不读配置 — 与 mobile_uniapp 一致）
  const [captchaId, setCaptchaId] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');

  // 页面状态
  const [isLoading, setIsLoading] = useState(false);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // 加载图形验证码
  useEffect(() => {
    refreshCaptcha();
  }, []);

  // 刷新图形验证码
  const refreshCaptcha = async () => {
    try {
      setFormErrors((prev) => ({ ...prev, captchaCode: '' }));

      let captcha;
      if (captchaId) {
        captcha = await AuthManager.getCaptcha(captchaId);
      } else {
        captcha = await AuthManager.getCaptchaSimple();
      }

      if (!captcha || !captcha.img) {
        throw new Error(t('auth.errors.getCaptchaFailed'));
      }

      setCaptchaId(captcha.id);
      setCaptchaImage(captcha.img);
    } catch (error: any) {
      console.error('获取图形验证码失败:', error);
      setFormErrors((prev) => ({
        ...prev,
        captchaCode: error.message || t('auth.errors.captchaUnavailable'),
      }));
      throw error;
    }
  };

  // 发送短信动态码
  const handleSendMobileCode = async () => {
    if (!validate.mobile(mobile)) {
      setFormErrors((prev) => ({ ...prev, mobile: t('auth.errors.enterCorrectMobile') }));
      return false;
    }

    if (!captchaCode) {
      setFormErrors((prev) => ({ ...prev, captchaCode: t('auth.errors.enterCaptcha') }));
      return false;
    }

    try {
      const result = await AuthManager.sendTripartiteMobileCode(
        mobile,
        captchaId,
        captchaCode
      );

      if (result && result.key) {
        setDynaCodeKey(result.key);
        setFormErrors({});
        return true;
      }
    } catch (error: any) {
      setFormErrors((prev) => ({
        ...prev,
        mobile: error.message || t('auth.errors.sendCodeFailed'),
      }));
      refreshCaptcha();
    }
    return false;
  };

  // 提交绑定
  const handleBindMobile = async () => {
    const errors: Record<string, string> = {};

    if (!validate.mobile(mobile)) {
      errors.mobile = t('auth.errors.enterCorrectMobile');
    }
    if (!captchaCode) {
      errors.captchaCode = t('auth.errors.enterCaptcha');
    }
    if (!dynaCode) {
      errors.dynaCode = t('auth.errors.enterDynaCode');
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    setFormErrors({});
    setIsLoading(true);

    try {
      const authData = {
        wx_openid: wxOpenid,
        wx_unionid: wxUnionid,
        headimg: avatar,
        nickname,
      };

      const result = await AuthManager.loginWithWechatMobile(
        authData,
        mobile,
        dynaCodeKey,
        dynaCode,
        captchaId,
        captchaCode
      );

      if (result && result.token) {
        api.setAuthToken(result.token);
        const userInfo = await AuthManager.getMemberInfo();
        await login(result.token, userInfo);
        router.replace('Main');
      } else {
        setFormErrors({ global: t('auth.bindMobile.bindFailed') });
      }
    } catch (error: any) {
      console.error('绑定手机号失败:', error);
      setFormErrors({
        global: error.message || t('auth.bindMobile.bindFailed'),
      });
      refreshCaptcha();
    } finally {
      setIsLoading(false);
    }
  };

  // 返回登录页
  const handleCancel = () => {
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
            onPress={handleCancel}
          >
            <MaterialIcons name="close" size={24} color={colors.onSurface} />
          </TouchableOpacity>

          {/* 头部 */}
          <View style={styles.header}>
            {avatar ? (
              <Avatar.Image size={64} source={{ uri: avatar }} style={styles.avatar} />
            ) : (
              <Avatar.Icon size={64} icon="account" style={styles.avatar} />
            )}
            <Text variant="headlineSmall" style={[styles.title, { color: colors.onSurface }]}>
              {t('auth.bindMobile.title')}
            </Text>
            <Text variant="bodyMedium" style={{ color: colors.text.secondary }}>
              {nickname ? t('auth.bindMobile.greeting', { nickname }) : t('auth.bindMobile.greetingFallback')}
            </Text>
            <Text variant="bodySmall" style={[styles.tip, { color: colors.text.secondary }]}>
              {t('auth.bindMobile.hint')}
            </Text>
          </View>

          {/* 表单 */}
          <View style={styles.form}>
            {/* 手机号 */}
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
            <View>
              <View style={styles.captchaContainer}>
                <TextInput
                  label={t('auth.login.captchaLabel')}
                  value={captchaCode}
                  onChangeText={(text) => {
                    setCaptchaCode(text);
                    if (formErrors.captchaCode) {
                      setFormErrors((prev) => ({ ...prev, captchaCode: '' }));
                    }
                  }}
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

            {/* 短信动态码 */}
            <View>
              <View style={styles.codeContainer}>
                <TextInput
                  label={t('auth.bindMobile.dynaCodeLabel')}
                  value={dynaCode}
                  onChangeText={(text) => {
                    setDynaCode(text);
                    if (formErrors.dynaCode) {
                      setFormErrors((prev) => ({ ...prev, dynaCode: '' }));
                    }
                  }}
                  keyboardType="number-pad"
                  maxLength={6}
                  error={!!formErrors.dynaCode}
                  style={[styles.input, styles.codeInput]}
                />
                <CountdownButton
                  onPress={handleSendMobileCode}
                  disabled={!validate.mobile(mobile) || !captchaCode}
                />
              </View>
              {formErrors.dynaCode && (
                <Text style={[styles.errorText, { color: colors.error }]}>
                  {formErrors.dynaCode}
                </Text>
              )}
            </View>
          </View>

          {/* 错误提示 */}
          {formErrors.global && (
            <Text style={[styles.globalError, { color: colors.error }]}>
              {formErrors.global}
            </Text>
          )}

          {/* 保存按钮 */}
          <Button
            mode="contained"
            onPress={handleBindMobile}
            loading={isLoading}
            disabled={isLoading}
            style={styles.saveButton}
            contentStyle={styles.saveButtonContent}
          >
            {t('auth.bindMobile.save')}
          </Button>

          {/* 取消按钮 */}
          <Button
            mode="text"
            onPress={handleCancel}
            disabled={isLoading}
            style={styles.cancelButton}
          >
            {t('auth.bindMobile.skip')}
          </Button>
        </ScrollView>
      </KeyboardAvoidingView>
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
    gap: 8,
  },
  avatar: {
    marginBottom: 4,
  },
  title: {
    fontWeight: 'bold',
  },
  tip: {
    textAlign: 'center',
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
    fontSize: 13,
    marginTop: 8,
  },
  saveButton: {
    borderRadius: 8,
    marginTop: 16,
  },
  saveButtonContent: {
    height: 48,
  },
  cancelButton: {
    marginTop: 8,
  },
});
