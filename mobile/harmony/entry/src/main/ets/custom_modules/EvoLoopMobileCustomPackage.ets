import { RNPackage, TurboModulesFactory } from '@rnoh/react-native-openharmony/ts';
import type { TurboModule, TurboModuleContext } from '@rnoh/react-native-openharmony/ts';
import { RNLiveAudioStream } from '../codegen/generated/turboModules/RNLiveAudioStream';
import { RNEvoLoopDeviceModule as RNEvoLoopDeviceSpec } from '../codegen/generated/turboModules/RNEvoLoopDeviceModule';
import { RNVoiceEngine } from '../codegen/generated/turboModules/RNVoiceEngine';
import { RNLiveAudioStreamTurboModule } from './RNLiveAudioStreamTurboModule';
import { RNEvoLoopDeviceModule } from './RNEvoLoopDeviceModule';
import { RNVoiceEngineTurboModule } from './RNVoiceEngineTurboModule';

class EvoLoopMobileCustomTurboModulesFactory extends TurboModulesFactory {
  createTurboModule(name: string): TurboModule | null {
    if (name === RNLiveAudioStream.NAME) {
      return new RNLiveAudioStreamTurboModule(this.ctx);
    } else if (name === RNEvoLoopDeviceSpec.NAME) {
      return new RNEvoLoopDeviceModule(this.ctx);
    } else if (name === RNVoiceEngine.NAME) {
      return new RNVoiceEngineTurboModule(this.ctx);
    }
    return null;
  }

  hasTurboModule(name: string): boolean {
    return name === RNLiveAudioStream.NAME || name === RNEvoLoopDeviceSpec.NAME || name === RNVoiceEngine.NAME;
  }
}

export class EvoLoopMobileCustomPackage extends RNPackage {
  createTurboModulesFactory(ctx: TurboModuleContext): TurboModulesFactory {
    return new EvoLoopMobileCustomTurboModulesFactory(ctx);
  }
}
