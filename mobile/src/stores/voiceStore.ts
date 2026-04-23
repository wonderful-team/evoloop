// 语音会话状态管理

import { create } from 'zustand';
import { VoiceSession, ChatMessage, TaskCommand, VoiceSessionState } from '@/types/voice';

interface VoiceState {
  currentSession: VoiceSession | null;
  sessionId: string | null;
  sessionState: VoiceSessionState;
  messages: ChatMessage[];
  currentCommand: TaskCommand | null;
  isRecording: boolean;
  isProcessing: boolean;
  isPlaying: boolean;
  transcription: string;

  // Actions
  createSession: () => void;
  startSession: (sessionId: string) => void;
  endSession: () => void;
  setSessionState: (state: VoiceSessionState) => void;
  addMessage: (message: ChatMessage) => void;
  updateLastMessage: (updates: Partial<ChatMessage>) => void;
  setCurrentCommand: (command: TaskCommand | null) => void;
  updateCommandStatus: (status: TaskCommand['status']) => void;
  confirmCurrentCommand: (confirmed: boolean) => void;
  setRecording: (recording: boolean) => void;
  setProcessing: (processing: boolean) => void;
  setPlaying: (playing: boolean) => void;
  setTranscription: (text: string) => void;
  appendTranscription: (text: string) => void;
  clearMessages: () => void;
}

export const useVoiceStore = create<VoiceState>((set, get) => ({
  currentSession: null,
  sessionId: null,
  sessionState: 'idle',
  messages: [],
  currentCommand: null,
  isRecording: false,
  isProcessing: false,
  isPlaying: false,
  transcription: '',

  createSession: () => {
    const session: VoiceSession = {
      id: `session_${Date.now()}`,
      state: 'idle',
      messages: [],
      startTime: Date.now(),
    };
    set({
      currentSession: session,
      sessionId: session.id,
      sessionState: 'idle',
      messages: [],
      currentCommand: null,
      transcription: '',
    });
  },

  startSession: (sessionId: string) => {
    const session: VoiceSession = {
      id: sessionId,
      state: 'connecting',
      messages: [],
      startTime: Date.now(),
    };
    set({
      currentSession: session,
      sessionId,
      sessionState: 'connecting',
      messages: [],
      currentCommand: null,
      transcription: '',
    });
  },

  endSession: () => {
    const { currentSession } = get();
    if (currentSession) {
      set({
        currentSession: {
          ...currentSession,
          state: 'idle',
          endTime: Date.now(),
        },
        sessionState: 'idle',
        isRecording: false,
        isProcessing: false,
      });
    }
  },

  setSessionState: (state: VoiceSessionState) => {
    set((prev) => ({
      sessionState: state,
      currentSession: prev.currentSession
        ? { ...prev.currentSession, state }
        : null,
    }));
  },

  addMessage: (message) => {
    const { messages } = get();
    set({ messages: [...messages, message] });
  },

  updateLastMessage: (updates: Partial<ChatMessage>) => {
    const { messages } = get();
    if (messages.length === 0) return;

    const lastIndex = messages.length - 1;
    const updatedMessages = [...messages];
    updatedMessages[lastIndex] = { ...updatedMessages[lastIndex], ...updates };
    set({ messages: updatedMessages });
  },

  setCurrentCommand: (command) => set({ currentCommand: command }),

  updateCommandStatus: (status) => {
    const { currentCommand } = get();
    if (currentCommand) {
      set({
        currentCommand: { ...currentCommand, status },
      });
    }
  },

  confirmCurrentCommand: (confirmed: boolean) => {
    const { currentCommand } = get();
    if (currentCommand) {
      set({
        currentCommand: {
          ...currentCommand,
          status: confirmed ? 'confirmed' : 'cancelled',
        },
      });
    }
  },

  setRecording: (recording) => set({ isRecording: recording }),
  setProcessing: (processing) => set({ isProcessing: processing }),
  setPlaying: (playing) => set({ isPlaying: playing }),
  setTranscription: (text) => set({ transcription: text }),
  
  appendTranscription: (text) => {
    const { transcription } = get();
    set({ transcription: transcription + text });
  },

  clearMessages: () => set({ messages: [] }),
}));
