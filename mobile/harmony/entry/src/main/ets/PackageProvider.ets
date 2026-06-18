import type { RNPackageContext, RNPackage } from '@rnoh/react-native-openharmony';
import { createRNOHPackages as createRNOHPackagesAutolinking } from "./RNOHPackagesFactory"
import { EvoLoopMobileCustomPackage } from "./custom_modules/EvoLoopMobileCustomPackage"
import GestureHandlerPackage from '@react-native-oh-tpl/react-native-gesture-handler';

// Manual package imports for skipped libraries
import { ReanimatedPackage } from '@react-native-ohos/react-native-reanimated';
import { DocumentPickerPackage } from '@react-native-oh-tpl/react-native-document-picker/ts';
import { FsPackage } from '@react-native-oh-tpl/react-native-fs';
import { PermissionsPackage } from '@react-native-ohos/react-native-permissions';
import { WebViewPackage } from '@react-native-ohos/react-native-webview';
import { AsyncStoragePackage } from '@react-native-oh-tpl/async-storage';
import { RNAudioRecorderPlayerPackage } from '@react-native-oh-tpl/react-native-audio-recorder-player';
import { SafeAreaViewPackage } from '@react-native-ohos/react-native-safe-area-context';
import { RNCVideoPackage } from '@react-native-ohos/react-native-video/ts';
import { ImageCropPickerPackage } from '@react-native-ohos/react-native-image-crop-picker';
import { RNSharePackage } from '@react-native-oh-tpl/react-native-share';
import { RNHapticFeedbackPackage } from '@react-native-oh-tpl/react-native-haptic-feedback';
import { RNLocalizePackage } from '@react-native-oh-tpl/react-native-localize';
import { ClipboardPackage } from '@react-native-ohos/clipboard';
import { VisionCameraModulePackage, VisionCameraViewPackage } from '@react-native-ohos/react-native-vision-camera';

export function getRNOHPackages(ctx: RNPackageContext): RNPackage[] {
  return [
    ...createRNOHPackagesAutolinking(ctx),
    new EvoLoopMobileCustomPackage(ctx),
    new GestureHandlerPackage(ctx),
    new ReanimatedPackage(ctx),
    new DocumentPickerPackage(ctx),
    new FsPackage(ctx),
    new PermissionsPackage(ctx),
    new WebViewPackage(ctx),
    new AsyncStoragePackage(ctx),
    new RNAudioRecorderPlayerPackage(ctx),
    new SafeAreaViewPackage(ctx),
    new RNCVideoPackage(ctx),
    new ImageCropPickerPackage(ctx),
    new RNSharePackage(ctx),
    new RNHapticFeedbackPackage(ctx),
    new RNLocalizePackage(ctx),
    new ClipboardPackage(ctx),
    new VisionCameraModulePackage(ctx),
    new VisionCameraViewPackage(ctx)
  ];
}
