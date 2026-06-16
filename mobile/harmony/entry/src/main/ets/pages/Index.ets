import {
  AnyJSBundleProvider,
  MetroJSBundleProvider,
  RNApp,
  RNOHErrorDialog,
  ResourceJSBundleProvider,
  RNOHCoreContext
} from '@rnoh/react-native-openharmony';
import { getRNOHPackages } from '../PackageProvider';

@Entry
@Component
struct Index {
  @StorageLink('RNOHCoreContext') private rnohCoreContext: RNOHCoreContext | undefined = undefined

  onBackPress(): boolean | undefined {
    this.rnohCoreContext?.dispatchBackPress()
    return true
  }

  build() {
    Column() {
      if (this.rnohCoreContext) {
        if (this.rnohCoreContext?.isDebugModeEnabled) {
          RNOHErrorDialog({ ctx: this.rnohCoreContext })
        }
        RNApp({
          rnInstanceConfig: {
            name: "EvoLoopMobile",
            createRNPackages: getRNOHPackages,
            fontResourceByFontFamily: {
              'Material Icons': $rawfile('fonts/MaterialIcons.ttf'),
              'MaterialIcons': $rawfile('fonts/MaterialIcons.ttf'),
              'Material Design Icons': $rawfile('fonts/MaterialCommunityIcons.ttf'),
              'MaterialCommunityIcons': $rawfile('fonts/MaterialCommunityIcons.ttf')
            },
            enableDebugger: this.rnohCoreContext?.isDebugModeEnabled,
          },
          appKey: "EvoLoopMobile",
          jsBundleProvider: this.rnohCoreContext?.isDebugModeEnabled ?
            new AnyJSBundleProvider([
              new MetroJSBundleProvider(),
              new ResourceJSBundleProvider(this.rnohCoreContext.uiAbilityContext.resourceManager, 'hermes_bundle.hbc'),
            ]) :
            /**
             * NOTE: The HBC format is recommended for Hermes in a production environment. HBC provides better performance and loading times.
             */
            new ResourceJSBundleProvider(this.rnohCoreContext.uiAbilityContext.resourceManager, 'hermes_bundle.hbc'),
        })
      }
    }
    .height('100%')
    .width('100%')
  }
}
