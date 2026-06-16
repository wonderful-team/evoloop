import AudioRecorderPlayer, {
    AudioEncoderAndroidType,
    AudioSourceAndroidType,
    AVEncoderAudioQualityIOSType,
    AVEncodingOption,
  } from 'react-native-audio-recorder-player';
  import { Platform, PermissionsAndroid } from 'react-native';
  import RNFS from 'react-native-fs';
  
  class AudioRecorder {
    private audioRecorderPlayer: AudioRecorderPlayer;
    private isRecording: boolean = false;
    private isPaused: boolean = false;
  
    constructor() {
      this.audioRecorderPlayer = new AudioRecorderPlayer();
      // 设置显示日志的级别
      this.audioRecorderPlayer.setSubscriptionDuration(0.1);
    }
  
    private async checkPermissions(): Promise<boolean> {
      if (Platform.OS === 'android') {
        try {
          const grants = await PermissionsAndroid.requestMultiple([
            PermissionsAndroid.PERMISSIONS.WRITE_EXTERNAL_STORAGE,
            PermissionsAndroid.PERMISSIONS.READ_EXTERNAL_STORAGE,
            PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          ]);
  
          if (
            grants['android.permission.WRITE_EXTERNAL_STORAGE'] === PermissionsAndroid.RESULTS.GRANTED &&
            grants['android.permission.READ_EXTERNAL_STORAGE'] === PermissionsAndroid.RESULTS.GRANTED &&
            grants['android.permission.RECORD_AUDIO'] === PermissionsAndroid.RESULTS.GRANTED
          ) {
            return true;
          }
          console.warn('Permissions denied');
          return false;
        } catch (err) {
          console.warn(err);
          return false;
        }
      } else if (Platform.OS === 'harmony') {
        const { requestMicrophonePermission } = require('@/utils/permissions');
        return requestMicrophonePermission();
      }
      return true;
    }
  
    public async startRecording(fileName?: string): Promise<string | undefined> {
      const hasPermission = await this.checkPermissions();
      if (!hasPermission) return undefined;
  
      if (this.isRecording) return undefined;
  
      const path = Platform.select({
        ios: `${fileName || 'hello'}.m4a`,
        android: `${RNFS.CachesDirectoryPath}/${fileName || 'hello'}.mp3`,
        harmony: `${RNFS.CachesDirectoryPath}/${fileName || 'hello'}.mp3`,
      });
  
      const audioSet = {
        AudioEncoderAndroid: AudioEncoderAndroidType.AAC,
        AudioSourceAndroid: AudioSourceAndroidType.MIC,
        AVEncoderAudioQualityKeyIOS: AVEncoderAudioQualityIOSType.high,
        AVNumberOfChannelsKeyIOS: 2,
        AVFormatIDKeyIOS: AVEncodingOption.aac,
      };
  
      try {
        const result = await this.audioRecorderPlayer.startRecorder(path, audioSet);
        this.audioRecorderPlayer.addRecordBackListener((e) => {
          // 可以在这里处理录音进度更新
          return;
        });
        this.isRecording = true;
        this.isPaused = false;
        return result;
      } catch (error) {
        console.error('Failed to start recording', error);
        return undefined;
      }
    }
  
    public async stopRecording(): Promise<string | undefined> {
      if (!this.isRecording) return undefined;
  
      try {
        const result = await this.audioRecorderPlayer.stopRecorder();
        this.audioRecorderPlayer.removeRecordBackListener();
        this.isRecording = false;
        this.isPaused = false;
        return result;
      } catch (error) {
        console.error('Failed to stop recording', error);
        return undefined;
      }
    }
  
    public async pauseRecording(): Promise<string | undefined> {
      if (!this.isRecording || this.isPaused) return undefined;
  
      try {
        const result = await this.audioRecorderPlayer.pauseRecorder();
        this.isPaused = true;
        return result;
      } catch (error) {
        console.error('Failed to pause recording', error);
        return undefined;
      }
    }
  
    public async resumeRecording(): Promise<string | undefined> {
      if (!this.isRecording || !this.isPaused) return undefined;
  
      try {
        const result = await this.audioRecorderPlayer.resumeRecorder();
        this.isPaused = false;
        return result;
      } catch (error) {
        console.error('Failed to resume recording', error);
        return undefined;
      }
    }
  }
  
  export const audioRecorder = new AudioRecorder();
  export default audioRecorder;
  
