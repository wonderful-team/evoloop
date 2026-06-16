/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */

import { Want, insightIntent, AbilityConstant } from '@kit.AbilityKit';
import { RNAbility, RNOHCoreContext, RNInstance } from '@rnoh/react-native-openharmony';

export default class EntryAbility extends RNAbility {
  override getPagePath() {
    return 'pages/Index';
  }

  override getRNOHWorkerScriptUrl() {
    return "entry/ets/workers/RNOHWorker.ets"
  }

  override onCreate(want: Want, launchParam?: AbilityConstant.LaunchParam) {
    super.onCreate(want, launchParam);
    this.checkWantParameters(want);
  }

  override onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    super.onNewWant(want, launchParam);
    this.checkWantParameters(want);
  }

  private checkWantParameters(want: Want) {
    if (want && want.parameters) {
      const intentNameObj: Object | undefined = want.parameters['intent.name'] || want.parameters['ohos.insightIntent.executeParam.name'];
      const queryTextObj: Object | undefined = want.parameters['queryText'];
      
      const intentName: string = intentNameObj ? intentNameObj.toString() : '';
      const queryText: string = queryTextObj ? queryTextObj.toString() : '';
      
      console.info(`[EntryAbility] checkWantParameters: intentName=${intentName}, queryText=${queryText}`);
      if (intentName === 'PlayVoiceChat' && queryText) {
        setTimeout(() => {
          this.handleVoiceIntent(queryText);
        }, 1500);
      }
    }
  }

  private handleVoiceIntent(queryText: string) {
    console.info(`[EntryAbility] 触发语音意图，内容: ${queryText}`);
    const rnohCoreContext: RNOHCoreContext | undefined = AppStorage.get<RNOHCoreContext>('RNOHCoreContext');
    if (queryText && rnohCoreContext) {
      rnohCoreContext._rnohCoreContextDeps.rnInstanceRegistry.forEach((rnInstance: RNInstance) => {
        rnInstance.emitDeviceEvent('onSystemVoiceIntent', { 'text': queryText });
      });
    }
  }

  /**
   * 鸿蒙系统意图执行回调
   */
  onExecuteInsightIntent(
    name: string,
    param: Record<string, Object>,
    pageMode: insightIntent.ExecuteMode
  ): insightIntent.ExecuteResult | Promise<insightIntent.ExecuteResult> {
    console.info(`[EntryAbility] 收到系统意图: name=${name}, param=${JSON.stringify(param)}`);

    if (name === 'PlayVoiceChat') {
      const queryTextObj: Object | undefined = param['queryText'];
      const queryText: string = queryTextObj ? queryTextObj.toString() : '';
      if (queryText) {
        this.handleVoiceIntent(queryText);
      }

      return {
        code: 0,
        result: {
          message: 'Intent executed successfully'
        }
      };
    }

    return {
      code: -1,
      result: {
        message: 'Unsupported intent'
      }
    };
  }
}
