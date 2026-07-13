import type { TurboModule } from 'react-native';
import { TurboModuleRegistry, NativeModules, Platform } from 'react-native';

export interface Spec extends TurboModule {
  getPushToken(): Promise<string>;
  requestNotificationPermission(): Promise<boolean>;
}

const isTurboModule = !!(global as any).__turboModuleProxy;

export default (Platform.OS !== 'harmony' && isTurboModule
  ? TurboModuleRegistry.getEnforcing<Spec>('RNEvoLoopDeviceModule')
  : NativeModules.RNEvoLoopDeviceModule) as Spec;
