import type { TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

export interface Spec extends TurboModule {
  getPushToken(): Promise<string>;
  requestNotificationPermission(): Promise<boolean>;
}

export default TurboModuleRegistry.getEnforcing<Spec>('RNEvoLoopDeviceModule');
