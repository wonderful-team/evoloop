import { TurboModule, TurboModuleContext } from '@rnoh/react-native-openharmony/ts';
import { RNEvoLoopDeviceModule } from '../codegen/generated/turboModules/RNEvoLoopDeviceModule';
import { pushService } from '@kit.PushKit';
import { notificationManager } from '@kit.NotificationKit';
import { BusinessError } from '@kit.BasicServicesKit';

export class RNEvoLoopDeviceModule extends TurboModule implements RNEvoLoopDeviceModule.Spec {
  constructor(ctx: TurboModuleContext) {
    super(ctx);
  }

  public async getPushToken(): Promise<string> {
    console.info(`[RNEvoLoopDeviceModule] getPushToken requested`);
    try {
      const token = await pushService.getToken();
      console.info(`[RNEvoLoopDeviceModule] Push token obtained successfully: ${token}`);
      return token;
    } catch (err) {
      const error = err as BusinessError;
      console.error(`[RNEvoLoopDeviceModule] Failed to get push token: code=${error.code}, msg=${error.message}`);
      throw new Error(`Failed to get push token: ${error.message}`);
    }
  }

  public async requestNotificationPermission(): Promise<boolean> {
    console.info(`[RNEvoLoopDeviceModule] requestNotificationPermission requested`);
    try {
      const isEnabled = await notificationManager.isNotificationEnabled();
      if (isEnabled) {
        console.info(`[RNEvoLoopDeviceModule] Notification permission already enabled`);
        return true;
      }
      
      await notificationManager.requestEnableNotification(this.ctx.uiAbilityContext);
      const nowEnabled = await notificationManager.isNotificationEnabled();
      console.info(`[RNEvoLoopDeviceModule] Notification permission request result: ${nowEnabled}`);
      return nowEnabled;
    } catch (err) {
      const error = err as BusinessError;
      console.error(`[RNEvoLoopDeviceModule] Failed to request notification permission: code=${error.code}, msg=${error.message}`);
      return false;
    }
  }
}
