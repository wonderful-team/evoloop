import { createNavigationContainerRef, StackActions } from '@react-navigation/native';

export const navigationRef = createNavigationContainerRef<any>();

export const router = {
  push: (name: string, params?: object) => {
    if (navigationRef.isReady()) {
      navigationRef.dispatch(StackActions.push(name, params));
    }
  },
  replace: (name: string, params?: object) => {
    if (navigationRef.isReady()) {
      navigationRef.dispatch(StackActions.replace(name, params));
    }
  },
  back: () => {
    if (navigationRef.isReady()) {
      const state = navigationRef.getState();
      // 检查是否可以返回（路由栈深度 > 1）
      const canGoBack = state?.routes?.length > 1;
      if (canGoBack) {
        navigationRef.goBack();
      }
      return canGoBack;
    }
    return false;
  },
  navigate: (name: string, params?: object) => {
    if (navigationRef.isReady()) {
      navigationRef.navigate(name as never, params as never);
    }
  },
};
