import { Platform } from 'react-native';
import { request, PERMISSIONS, RESULTS } from 'react-native-permissions';

/**
 * Request Microphone permission safely on Android, iOS, and HarmonyOS
 */
export async function requestMicrophonePermission(): Promise<boolean> {
  try {
    if (Platform.OS === 'android') {
      const res = await request(PERMISSIONS.ANDROID.RECORD_AUDIO);
      return res === RESULTS.GRANTED;
    } else if (Platform.OS === 'ios') {
      const res = await request(PERMISSIONS.IOS.MICROPHONE);
      return res === RESULTS.GRANTED;
    } else if (Platform.OS === 'harmony') {
      const harmonyPermissions = (PERMISSIONS as any).HARMONY;
      if (harmonyPermissions && harmonyPermissions.MICROPHONE) {
        const res = await request(harmonyPermissions.MICROPHONE);
        return res === RESULTS.GRANTED;
      }
    }
  } catch (err) {
    console.error('Request microphone permission failed:', err);
  }
  return false;
}

/**
 * Request Camera permission safely on Android, iOS, and HarmonyOS
 */
export async function requestCameraPermission(): Promise<boolean> {
  try {
    if (Platform.OS === 'android') {
      const res = await request(PERMISSIONS.ANDROID.CAMERA);
      return res === RESULTS.GRANTED;
    } else if (Platform.OS === 'ios') {
      const res = await request(PERMISSIONS.IOS.CAMERA);
      return res === RESULTS.GRANTED;
    } else if (Platform.OS === 'harmony') {
      const harmonyPermissions = (PERMISSIONS as any).HARMONY;
      if (harmonyPermissions && harmonyPermissions.CAMERA) {
        const res = await request(harmonyPermissions.CAMERA);
        return res === RESULTS.GRANTED;
      }
    }
  } catch (err) {
    console.error('Request camera permission failed:', err);
  }
  return false;
}

/**
 * Request Photo/Video Library permission safely on Android, iOS, and HarmonyOS
 */
export async function requestPhotoLibraryPermission(): Promise<boolean> {
  try {
    if (Platform.OS === 'android') {
      // For Android 13+ (API 33+), check if we need READ_MEDIA_IMAGES or READ_MEDIA_VIDEO
      // Fallback to READ_EXTERNAL_STORAGE for older versions
      if (Platform.Version >= 33) {
        const resImages = await request(PERMISSIONS.ANDROID.READ_MEDIA_IMAGES);
        return resImages === RESULTS.GRANTED;
      } else {
        const res = await request(PERMISSIONS.ANDROID.READ_EXTERNAL_STORAGE);
        return res === RESULTS.GRANTED;
      }
    } else if (Platform.OS === 'ios') {
      const res = await request(PERMISSIONS.IOS.PHOTO_LIBRARY);
      return res === RESULTS.GRANTED || res === RESULTS.LIMITED;
    } else if (Platform.OS === 'harmony') {
      const harmonyPermissions = (PERMISSIONS as any).HARMONY;
      if (harmonyPermissions && harmonyPermissions.READ_IMAGEVIDEO) {
        const res = await request(harmonyPermissions.READ_IMAGEVIDEO);
        return res === RESULTS.GRANTED;
      }
    }
  } catch (err) {
    console.error('Request photo library permission failed:', err);
  }
  return false;
}
