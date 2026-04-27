// NLS 语音识别状态共享 Store
// 将高频变化的状态（currentText, volume）从 ChatScreen 中抽离，
// 避免语音识别过程中整页重渲染导致按钮卡顿。
// useNLS Hook 更新此 store，各消费组件自行订阅。

import { create } from 'zustand';

export type NLSStoreState = 'idle' | 'connecting' | 'connected' | 'recognizing' | 'error';

interface NLSStore {
  state: NLSStoreState;
  isRecording: boolean;
  currentText: string;
  volume: number;
  setState: (state: NLSStoreState) => void;
  setCurrentText: (text: string) => void;
  setVolume: (volume: number) => void;
  reset: () => void;
}

export const useNLSStore = create<NLSStore>((set) => ({
  state: 'idle',
  isRecording: false,
  currentText: '',
  volume: 0,
  setState: (state) => set({
    state,
    isRecording: state === 'connected' || state === 'recognizing',
  }),
  setCurrentText: (text) => set({ currentText: text }),
  setVolume: (volume) => set({ volume }),
  reset: () => set({ state: 'idle', isRecording: false, currentText: '', volume: 0 }),
}));
