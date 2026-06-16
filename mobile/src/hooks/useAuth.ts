// 认证 Hook

import { useCallback } from 'react';
import { router } from '@/utils/navigation';
import { useAuthStore, tokenStorage } from '@/stores/authStore';
import { useLoading } from './useLoading';
import { AuthManager } from '@/services/auth/AuthManager';
import { authApi } from '@/services/api/auth';
import {
  LoginResponse,
  MobileLoginRequest,
  AccountLoginRequest,
  WechatAuthData,
  RegisterRequest,
} from '@/types';

export function useAuth() {
  const { isLoggedIn, userInfo, login, logout } = useAuthStore();
  const { isLoading, error, execute, reset } = useLoading({
    onError: (err) => {
      console.warn('Auth error:', err);
    },
  });

  // 手机号登录
  const loginWithMobile = useCallback(
    async (data: MobileLoginRequest) => {
      const result = await execute(
        AuthManager.loginWithMobile(data.mobile, data.key, data.code)
      );

      if (result) {
        // 先保存 token，以便后续请求使用
        await tokenStorage.setToken(result.token);
        // 更新 store 中的 token（不标记为已登录，等获取到用户信息后再标记）
        useAuthStore.setState({ token: result.token });

        try {
          // 登录成功后获取用户信息
          const userInfo = await AuthManager.getMemberInfo();
          await login(result.token, userInfo);
          router.replace('Main');
        } catch (error) {
          // 如果获取用户信息失败，清除 token
          await tokenStorage.removeToken();
          useAuthStore.setState({ token: null });
          throw error;
        }
      }

      return result;
    },
    [execute, login]
  );

  // 账号密码登录
  const loginWithAccount = useCallback(
    async (data: AccountLoginRequest) => {
      const result = await execute(
        AuthManager.loginWithAccount(
          data.username,
          data.password,
          data.captcha_id,
          data.captcha_code
        )
      );

      if (result) {
        // 先保存 token，以便后续请求使用
        await tokenStorage.setToken(result.token);
        useAuthStore.setState({ token: result.token });

        try {
          // 登录成功后获取用户信息
          const userInfo = await AuthManager.getMemberInfo();
          await login(result.token, userInfo);
          router.replace('Main');
        } catch (error) {
          // 如果获取用户信息失败，清除 token
          await tokenStorage.removeToken();
          useAuthStore.setState({ token: null });
          throw error;
        }
      }

      return result;
    },
    [execute, login]
  );

  // 微信登录 (使用 authData)
  const loginWithWechat = useCallback(
    async (authData: WechatAuthData) => {
      const result = await execute(AuthManager.loginWithWechat(authData));

      if (result) {
        // 如果是新用户，需要绑定手机号
        if (result.is_register) {
          // TODO: 跳转到绑定手机号页面
          router.push('BindMobile');
        } else {
          // 先保存 token，以便后续请求使用
          await tokenStorage.setToken(result.token);
          useAuthStore.setState({ token: result.token });

          try {
            // 登录成功后获取用户信息
            const userInfo = await AuthManager.getMemberInfo();
            await login(result.token, userInfo);
            router.replace('Main');
          } catch (error) {
            // 如果获取用户信息失败，清除 token
            await tokenStorage.removeToken();
            useAuthStore.setState({ token: null });
            throw error;
          }
        }
      }

      return result;
    },
    [execute, login]
  );

  // 微信 Code 登录 (EvoLoop Mobile App)
  const loginWithWechatCode = useCallback(
    async (code: string, appType: 'ios' | 'android' = 'ios') => {
      const result = await execute(AuthManager.loginWithWechatCode(code, appType));

      if (result) {
        // 如果是新用户，需要绑定手机号
        if (result.is_register) {
          // TODO: 跳转到绑定手机号页面
          router.push('BindMobile');
        } else {
          // 先保存 token，以便后续请求使用
          await tokenStorage.setToken(result.token);
          useAuthStore.setState({ token: result.token });

          try {
            // 登录成功后获取用户信息
            const userInfo = await AuthManager.getMemberInfo();
            await login(result.token, userInfo);
            router.replace('Main');
          } catch (error) {
            // 如果获取用户信息失败，清除 token
            await tokenStorage.removeToken();
            useAuthStore.setState({ token: null });
            throw error;
          }
        }
      }

      return result;
    },
    [execute, login]
  );

  // 手机号注册
  const registerWithMobile = useCallback(
    async (data: {
      mobile: string;
      key: string;
      code: string;
      password?: string;
      captcha_id?: string;
      captcha_code?: string;
      source_member?: string;
      nickname?: string;
      headimg?: string;
    }) => {
      const result = await execute(authApi.registerWithMobile(data));
      return result;
    },
    [execute]
  );

  // 用户名注册
  const registerWithUsername = useCallback(
    async (data: {
      username: string;
      password: string;
      captcha_id?: string;
      captcha_code?: string;
      source_member?: string;
      nickname?: string;
      headimg?: string;
    }) => {
      const result = await execute(authApi.registerWithUsername(data));
      return result;
    },
    [execute]
  );

  // 重置密码
  const resetPassword = useCallback(
    async (data: {
      mobile: string;
      key: string;
      code: string;
      password: string;
    }) => {
      const result = await execute(authApi.resetPassword(data));
      return result;
    },
    [execute]
  );

  // 登出
  const handleLogout = useCallback(async () => {
    await logout();
    await AuthManager.logout();
    router.replace('Auth');
  }, [logout]);

  // 发送手机验证码
  const sendMobileCode = useCallback(
    async (mobile: string, captchaId?: string, captchaCode?: string) => {
      return await execute(AuthManager.sendMobileCode(mobile, captchaId, captchaCode, 'login'));
    },
    [execute]
  );

  // 发送找回密码验证码
  const sendResetCode = useCallback(
    async (mobile: string, captchaId?: string, captchaCode?: string) => {
      return await execute(AuthManager.sendMobileCode(mobile, captchaId, captchaCode, 'reset'));
    },
    [execute]
  );

  // 发送微信绑定手机号的短信验证码
  const sendBindMobileCode = useCallback(
    async (mobile: string, captchaId?: string, captchaCode?: string) => {
      return await execute(AuthManager.sendTripartiteMobileCode(mobile, captchaId, captchaCode));
    },
    [execute]
  );

  // 注销账号
  const deleteAccount = useCallback(async () => {
    await execute(authApi.deleteAccount());
    await logout();
    router.replace('Auth');
  }, [execute, logout]);

  return {
    isLoggedIn,
    userInfo,
    isLoading,
    error,
    loginWithMobile,
    loginWithAccount,
    loginWithWechat,
    loginWithWechatCode,
    registerWithMobile,
    registerWithUsername,
    resetPassword,
    logout: handleLogout,
    sendMobileCode,
    sendResetCode,
    sendBindMobileCode,
    deleteAccount,
    resetError: reset,
  };
}
