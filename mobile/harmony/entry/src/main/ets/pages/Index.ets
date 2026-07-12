import {
  RNApp,
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
            enableDebugger: false,
          },
          appKey: "EvoLoopMobile",
          /**
           * NOTE: The HBC format is recommended for Hermes in a production environment.
           * HBC provides better performance and loading times.
           */
          jsBundleProvider:
            new ResourceJSBundleProvider(this.rnohCoreContext.uiAbilityContext.resourceManager, 'hermes_bundle.hbc'),
        })
      }
    }
    .height('100%')
    .width('100%')
  }
}
