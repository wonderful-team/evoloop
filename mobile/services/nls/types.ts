// 阿里云 NLS 类型定义

// NLS 消息类型
export enum NLSMessageType {
  // 请求指令
  START_TRANSCRIPTION = 'StartTranscription',
  STOP_TRANSCRIPTION = 'StopTranscription',
  
  // 响应事件
  TRANSCRIPTION_STARTED = 'TranscriptionStarted',
  SENTENCE_BEGIN = 'SentenceBegin',
  TRANSCRIPTION_RESULT_CHANGED = 'TranscriptionResultChanged',
  SENTENCE_END = 'SentenceEnd',
  TRANSCRIPTION_COMPLETED = 'TranscriptionCompleted',
  TASK_FAILED = 'TaskFailed',
}

// NLS 配置
export interface NLSConfig {
  appKey: string;
  token: string;
  url?: string; // 默认 wss://nls-gateway.aliyuncs.com/ws/v1
  sampleRate?: number; // 16000 或 8000
  format?: 'pcm' | 'opus';
}

// 开始识别请求
export interface StartTranscriptionRequest {
  header: {
    message_id: string;
    task_id: string;
    namespace: 'SpeechTranscriber';
    name: NLSMessageType.START_TRANSCRIPTION;
    appkey: string;
  };
  payload: {
    sample_rate?: number;
    format?: string;
    enable_intermediate_result?: boolean;
    enable_punctuation_prediction?: boolean;
    enable_inverse_text_normalization?: boolean;
    max_sentence_silence?: number; // 200-2000ms，默认 800ms
    enable_words?: boolean;
    disfluency?: boolean;
  };
}

// 识别结果
export interface NLSTranscriptionResult {
  header: {
    namespace: string;
    name: NLSMessageType;
    status: number;
    message_id: string;
    task_id: string;
    status_text?: string;
  };
  payload: {
    result?: string;
    index?: number;
    time?: number;
    confidence?: number;
    words?: Array<{
      text: string;
      startTime: number;
      endTime: number;
    }>;
    begin_time?: number;
  };
}

// NLS 回调
export interface NLSCallbacks {
  onConnected?: () => void;
  onDisconnected?: () => void;
  onError?: (error: Error) => void;
  
  // 识别回调
  onRecognitionStarted?: () => void;
  onResultChanged?: (text: string) => void; // 中间结果
  onSentenceEnd?: (text: string) => void;   // 一句结束
  onRecognitionCompleted?: () => void;
}

// 识别状态
export type NLSState = 'idle' | 'connecting' | 'connected' | 'recognizing' | 'error';
