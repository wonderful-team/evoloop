import { Platform } from 'react-native';

export interface EvoLoopDeviceInterface {
  getPushToken(): Promise<string>;
  requestNotificationPermission(): Promise<boolean>;
}

let EvoLoopDevice: EvoLoopDeviceInterface = {
  getPushToken: async () => {
    return '';
  },
  requestNotificationPermission: async () => {
    return false;
  }
};

if (Platform.OS === 'harmony') {
  try {
    const RNEvoLoopDeviceModule = require('../../specs/NativeEvoLoopDeviceModule').default;
    if (RNEvoLoopDeviceModule) {
      EvoLoopDevice = {
        getPushToken: async () => {
          try {
            return await RNEvoLoopDeviceModule.getPushToken();
          } catch (e) {
            console.warn('[EvoLoopDevice] Failed to get push token:', e);
            return '';
          }
        },
        requestNotificationPermission: async () => {
          try {
            return await RNEvoLoopDeviceModule.requestNotificationPermission();
          } catch (e) {
            console.warn('[EvoLoopDevice] Failed to request notification permission:', e);
            return false;
          }
        }
      };
    }
  } catch (e) {
    console.warn('[EvoLoopDevice] Failed to require NativeEvoLoopDeviceModule:', e);
  }
}

export default EvoLoopDevice;
