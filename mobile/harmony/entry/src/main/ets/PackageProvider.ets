import type { RNPackageContext, RNOHPackage } from '@rnoh/react-native-openharmony';
import { createRNOHPackages as createRNOHPackagesAutolinking } from "./RNOHPackagesFactory"
import { EvoLoopMobileCustomPackage } from "./custom_modules/EvoLoopMobileCustomPackage"

// Manual package imports for skipped libraries
import { ReanimatedPackage } from '@react-native-oh-tpl/react-native-reanimated';
import { DocumentPickerPackage } from '@react-native-oh-tpl/react-native-document-picker';
import { FsPackage } from '@react-native-oh-tpl/react-native-fs';
import { PermissionsPackage } from '@react-native-oh-tpl/react-native-permissions';
import { WebViewPackage } from '@react-native-oh-tpl/react-native-webview';
import { AsyncStoragePackage } from '@react-native-oh-tpl/async-storage';
import { RNAudioRecorderPlayerPackage } from '@react-native-oh-tpl/react-native-audio-recorder-player';
import { SafeAreaViewPackage } from '@react-native-oh-tpl/react-native-safe-area-context';
import { RNCVideoPackage } from '@react-native-oh-tpl/react-native-video';
import { NetInfoPackage } from '@react-native-oh-tpl/netinfo';
import { ImageCropPickerPackage } from '@react-native-oh-tpl/react-native-image-crop-picker';
import { RNSharePackage } from '@react-native-oh-tpl/react-native-share';
import { RNHapticFeedbackPackage } from '@react-native-oh-tpl/react-native-haptic-feedback';
import { RNLocalizePackage } from '@react-native-oh-tpl/react-native-localize';
import { ClipboardPackage } from '@react-native-oh-tpl/clipboard';
import { VisionCameraModulePackage, VisionCameraViewPackage } from '@react-native-ohos/react-native-vision-camera';

export function getRNOHPackages(ctx: RNPackageContext): RNOHPackage[] {
  return [
    ...createRNOHPackagesAutolinking(ctx),
    new EvoLoopMobileCustomPackage(ctx),
    new ReanimatedPackage(ctx),
    new DocumentPickerPackage(ctx),
    new FsPackage(ctx),
    new PermissionsPackage(ctx),
    new WebViewPackage(ctx),
    new AsyncStoragePackage(ctx),
    new RNAudioRecorderPlayerPackage(ctx),
    new SafeAreaViewPackage(ctx),
    new RNCVideoPackage(ctx),
    new NetInfoPackage(ctx),
    new ImageCropPickerPackage(ctx),
    new RNSharePackage(ctx),
    new RNHapticFeedbackPackage(ctx),
    new RNLocalizePackage(ctx),
    new ClipboardPackage(ctx),
    new VisionCameraModulePackage(ctx),
    new VisionCameraViewPackage(ctx)
  ];
}
