import worker, { ErrorEvent, MessageEvents, ThreadWorkerGlobalScope } from '@ohos.worker';
import {
  OnlineModelConfig,
  OnlineRecognizer,
  OnlineRecognizerConfig,
  OnlineStream,
} from 'sherpa_onnx';

const workerPort: ThreadWorkerGlobalScope = worker.workerPort;

let recognizer: OnlineRecognizer | null = null;
let currentStream: OnlineStream | null = null;
let sampleRate = 16000;

interface SamplesMessage {
  type: 'samples';
  samples: Float32Array;
  sampleRate: number;
}

interface InitMessage {
  type: 'init';
  modelDir: string;
  sampleRate: number;
  numThreads: number;
  silenceTimeoutMs: number;
}

interface StopMessage {
  type: 'stop';
}

type WorkerMessage = InitMessage | SamplesMessage | StopMessage;

function getOrCreateStream(): OnlineStream | null {
  if (!recognizer) {
    return null;
  }
  if (!currentStream) {
    currentStream = recognizer.createStream();
  }
  return currentStream;
}

function initRecognizer(config: InitMessage): void {
  try {
    sampleRate = config.sampleRate;

    console.info(`[SherpaAsrWorker] init with modelDir: ${config.modelDir}`);

    const modelConfig = new OnlineModelConfig();
    modelConfig.transducer.encoder = `${config.modelDir}/encoder-epoch-99-avg-1.int8.onnx`;
    modelConfig.transducer.decoder = `${config.modelDir}/decoder-epoch-99-avg-1.onnx`;
    modelConfig.transducer.joiner = `${config.modelDir}/joiner-epoch-99-avg-1.int8.onnx`;
    modelConfig.tokens = `${config.modelDir}/tokens.txt`;
    modelConfig.modelType = 'zipformer';
    modelConfig.numThreads = config.numThreads;

    const recognizerConfig = new OnlineRecognizerConfig();
    recognizerConfig.modelConfig = modelConfig;
    recognizerConfig.enableEndpoint = true;
    recognizerConfig.rule1MinTrailingSilence = config.silenceTimeoutMs / 1000;
    recognizerConfig.rule2MinTrailingSilence = config.silenceTimeoutMs / 1000;
    recognizerConfig.rule3MinUtteranceLength = 20.0;

    recognizer = new OnlineRecognizer(recognizerConfig);
    currentStream = recognizer.createStream();
    console.info('[SherpaAsrWorker] recognizer created');
    workerPort.postMessage({ type: 'init-done' });
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    console.error(`[SherpaAsrWorker] init failed: ${errMsg}`);
    workerPort.postMessage({ type: 'error', message: `init failed: ${errMsg}` });
  }
}

function processSamples(msg: SamplesMessage): void {
  if (!recognizer) {
    return;
  }

  const stream = getOrCreateStream();
  if (!stream) {
    return;
  }

  stream.acceptWaveform({ samples: msg.samples, sampleRate: msg.sampleRate });

  while (recognizer.isReady(stream)) {
    recognizer.decode(stream);
  }

  const result = recognizer.getResult(stream);
  if (result.text && result.text.trim() !== '') {
    workerPort.postMessage({ type: 'partial', text: result.text.trim() });
  }

  if (recognizer.isEndpoint(stream)) {
    const finalText = recognizer.getResult(stream).text;
    if (finalText && finalText.trim() !== '') {
      workerPort.postMessage({ type: 'final', text: finalText.trim() });
    }
    recognizer.reset(stream);
  }
}

workerPort.onmessage = (e: MessageEvents) => {
  const msg = e.data as WorkerMessage;

  if (msg.type === 'init') {
    initRecognizer(msg);
    return;
  }

  if (msg.type === 'samples') {
    processSamples(msg);
    return;
  }

  if (msg.type === 'stop') {
    currentStream = null;
    recognizer = null;
    return;
  }
};

workerPort.onmessageerror = (e: MessageEvents) => {
  workerPort.postMessage({ type: 'error', message: `message error: ${JSON.stringify(e)}` });
};

workerPort.onerror = (e: ErrorEvent) => {
  workerPort.postMessage({ type: 'error', message: `worker error: ${JSON.stringify(e)}` });
};
