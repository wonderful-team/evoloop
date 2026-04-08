// 微信登录后绑定手机号页面
// 参照 mobile_uniapp 的 ns-login.vue 实现

import React, { useState, useEffect } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import {
  Text,
  TextInput,
  Button,
  Avatar,
  ActivityIndicator,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useTheme } from '@/theme';
import { AuthManager } from '@/services/auth/AuthManager';
import { api } from '@/services/api/client';
import { useAuthStore } from '@/stores/authStore';
import { validate } from '@/utils/validate';
import { CountdownButton, CaptchaImage } from '@/components/auth';

export default function BindMobileScreen() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const { colors } = useTheme();
  const { login } = useAuthStore();

  // 微信授权信息（从路由参数传入）
  const wxOpenid = (params.wx_openid as string) || '';
  const wxUnionid = (params.wx_unionid as string) || '';
  const nickname = (params.nickname as string) || '';
  const avatar = (params.avatar as string) || '';

  // 表单状态
  const [mobile, setMobile] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');
  const [dynaCode, setDynaCode] = useState('');
  const [dynaCodeKey, setDynaCodeKey] = useState('');

  // 图形验证码
  const [captchaId, setCaptchaId] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [needCaptcha, setNeedCaptcha] = useState(false);

  // 页面状态
  const [isLoading, setIsLoading] = useState(false);
  const [isCheckingConfig, setIsCheckingConfig] = useState(true);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // 加载验证码配置
  useEffect(() => {
    loadCaptchaConfig();
  }, []);

  const loadCaptchaConfig = async () => {
    try {
      setIsCheckingConfig(true);
      const config = await AuthManager.getCaptchaConfig();

      if (config && config.shop_reception_login === 1) {
        setNeedCaptcha(true);
        try {
          await refreshCaptcha();
        } catch (captchaError: any) {
          console.warn('验证码服务不可用，暂时禁用:', captchaError);
          setNeedCaptcha(false);
        }
      }
    } catch (error: any) {
      console.error('获取验证码配置失败:', error);
      setNeedCaptcha(false);
    } finally {
      setIsCheckingConfig(false);
    }
  };

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

      if (!captcha || !captcha.id || !captcha.img) {
        throw new Error('获取验证码失败');
      }

      setCaptchaId(captcha.id);
      setCaptchaImage(captcha.img);
    } catch (error: any) {
      console.error('获取图形验证码失败:', error);
      setNeedCaptcha(false);
      setFormErrors((prev) => ({
        ...prev,
        captchaCode: error.message || '验证码服务暂时不可用',
      }));
      throw error;
    }
  };

  // 发送短信动态码
  const handleSendMobileCode = async () => {
    // 验证手机号
    if (!validate.mobile(mobile)) {
      setFormErrors((prev) => ({ ...prev, mobile: '请输入正确的手机号' }));
      return false;
    }

    // 如果需要图形验证码
    if (needCaptcha && !captchaCode) {
      setFormErrors((prev) => ({ ...prev, captchaCode: '请输入图形验证码' }));
      return false;
    }

    try {
      // 调用第三方登录专用的短信验证码接口
      const result = await AuthManager.sendTripartiteMobileCode(
        mobile,
        needCaptcha ? captchaId : undefined,
        needCaptcha ? captchaCode : undefined
      );

      if (result && result.key) {
        setDynaCodeKey(result.key);
        setFormErrors({});
        return true;
      }
    } catch (error: any) {
      setFormErrors((prev) => ({
        ...prev,
        mobile: error.message || '发送验证码失败',
      }));
      // 刷新图形验证码
      if (needCaptcha) {
        refreshCaptcha();
      }
    }
    return false;
  };

  // 提交绑定
  const handleBindMobile = async () => {
    // 表单验证
    const errors: Record<string, string> = {};

    if (!validate.mobile(mobile)) {
      errors.mobile = '请输入正确的手机号';
    }
    if (needCaptcha && !captchaCode) {
      errors.captchaCode = '请输入图形验证码';
    }
    if (!dynaCode) {
      errors.dynaCode = '请输入短信动态码';
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    setFormErrors({});
    setIsLoading(true);

    try {
      // 构造 authData（微信授权信息）
      const authData = {
        wx_openid: wxOpenid,
        wx_unionid: wxUnionid,
        headimg: avatar,
        nickname,
      };

      // 调用微信+手机号绑定登录接口
      const result = await AuthManager.loginWithWechatMobile(
        authData,
        mobile,
        dynaCodeKey,
        dynaCode
      );

      if (result && result.token) {
        // 登录成功，设置 token
        api.setAuthToken(result.token);
        // 获取用户信息
        const userInfo = await AuthManager.getMemberInfo();
        login(result.token, userInfo);
        // 跳转到首页
        router.replace('/(main)');
      } else {
        setFormErrors({ global: '绑定失败，请重试' });
      }
    } catch (error: any) {
      console.error('绑定手机号失败:', error);
      setFormErrors({
        global: error.message || '绑定失败，请重试',
      });
      // 刷新图形验证码
      if (needCaptcha) {
        refreshCaptcha();
      }
    } finally {
      setIsLoading(false);
    }
  };

  // 返回登录页
  const handleCancel = () => {
    router.back();
  };

  if (isCheckingConfig) {
    return (
      <SafeAreaView style={[styles.container, styles.center]}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>加载中...</Text>
      </SafeAreaView>
    );
  }

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
          {/* 头部 */}
          <View style={styles.header}>
            {avatar ? (
              <Avatar.Image size={64} source={{ uri: avatar }} style={styles.avatar} />
            ) : (
              <Avatar.Icon size={64} icon="account" style={styles.avatar} />
            )}
            <Text variant="headlineSmall" style={[styles.title, { color: colors.text.primary }]}>
              绑定手机号
            </Text>
            <Text variant="bodyMedium" style={{ color: colors.text.secondary }}>
              {nickname ? `你好，${nickname}` : '检测到您还未绑定手机号'}
            </Text>
            <Text variant="bodySmall" style={[styles.tip, { color: colors.text.tertiary }]}>
              为了方便您接收订单等信息，需要绑定手机号
            </Text>
          </View>

          {/* 表单 */}
          <View style={styles.form}>
            {/* 手机号 */}
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
            )}
            {formErrors.captchaCode && (
              <Text style={[styles.errorText, { color: colors.error }]}>
                {formErrors.captchaCode}
              </Text>
            )}

            {/* 短信动态码 */}
            <View style={styles.codeContainer}>
              <TextInput
                label="短信动态码"
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
                disabled={!validate.mobile(mobile) || (needCaptcha && !captchaCode)}
              />
            </View>
            {formErrors.dynaCode && (
              <Text style={[styles.errorText, { color: colors.error }]}>
                {formErrors.dynaCode}
              </Text>
            )}
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
            保存
          </Button>

          {/* 取消按钮 */}
          <Button
            mode="text"
            onPress={handleCancel}
            disabled={isLoading}
            style={styles.cancelButton}
          >
            暂不绑定，返回登录
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
  center: {
    justifyContent: 'center',
    alignItems: 'center',
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
  avatar: {
    marginBottom: 16,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 8,
  },
  tip: {
    marginTop: 4,
    textAlign: 'center',
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
  saveButton: {
    borderRadius: 8,
    marginBottom: 12,
  },
  saveButtonContent: {
    height: 48,
  },
  cancelButton: {
    marginTop: 8,
  },
  loadingText: {
    marginTop: 12,
    opacity: 0.6,
  },
});
