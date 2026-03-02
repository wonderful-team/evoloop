import React, { useState, useEffect, useRef } from "react"
import { View, TouchableOpacity, Text, StyleSheet, Animated, Dimensions } from "react-native"
import { Mic, Square, Loader2 } from "lucide-react-native"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useRealtimeVoice } from "../../hooks/useRealtimeVoice"

interface VoiceChatButtonProps {
  memberId: string
  threadId?: string
  projectId?: number
  onClose?: () => void
}

const { width } = Dimensions.get("window")

export const VoiceChatButton: React.FC<VoiceChatButtonProps> = ({
  memberId,
  threadId,
  projectId,
  onClose,
}) => {
  const { t } = useTranslation()
  const [showTranscript, setShowTranscript] = useState(false)
  const pulseAnim = useRef(new Animated.Value(1)).current
  const slideAnim = useRef(new Animated.Value(0)).current

  const {
    isSessionActive,
    isRecording,
    isProcessing,
    isAiSpeaking,
    error,
    userText,
    aiText,
    startSession,
    startRecording,
    stopRecording,
    interrupt,
    endSession,
  } = useRealtimeVoice({
    memberId,
    threadId,
    projectId,
    onSessionStarted: () => {
      setShowTranscript(true)
      Animated.spring(slideAnim, {
        toValue: 1,
        useNativeDriver: true,
      }).start()
    },
    onSessionEnded: () => {
      setShowTranscript(false)
      Animated.spring(slideAnim, {
        toValue: 0,
        useNativeDriver: true,
      }).start()
      onClose?.()
    },
    onChatComplete: (user, ai) => {
      console.log("Chat complete:", { user, ai })
    },
    onActionDispatched: (intent) => {
      toast.success(t("voice.actionDispatched", "任务已下发到设备"))
    },
    onError: (message) => {
      toast.error(message)
    },
  })

  // 录音动画
  useEffect(() => {
    if (isRecording) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.3,
            duration: 800,
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 800,
            useNativeDriver: true,
          }),
        ])
      ).start()
    } else {
      pulseAnim.setValue(1)
    }
  }, [isRecording])

  // 错误提示
  useEffect(() => {
    if (error) {
      toast.error(error)
    }
  }, [error])

  const handlePressIn = async () => {
    if (!isSessionActive) {
      await startSession()
    }
    await startRecording()
  }

  const handlePressOut = () => {
    if (isRecording) {
      stopRecording()
    }
  }

  const handleLongPress = () => {
    interrupt()
    toast.info(t("voice.interrupted", "已打断"))
  }

  const handleClose = () => {
    endSession()
  }

  // 获取按钮状态文本
  const getButtonText = () => {
    if (isProcessing) return t("voice.processing", "处理中...")
    if (isRecording) return t("voice.releaseToSend", "松开发送")
    if (isAiSpeaking) return t("voice.aiSpeaking", "AI 说话中...")
    return t("voice.holdToSpeak", "按住说话")
  }

  return (
    <View style={styles.container}>
      {/* 转录文本显示区域 */}
      {showTranscript && (
        <Animated.View
          style={[
            styles.transcriptContainer,
            {
              transform: [
                {
                  translateY: slideAnim.interpolate({
                    inputRange: [0, 1],
                    outputRange: [100, 0],
                  }),
                },
              ],
              opacity: slideAnim,
            },
          ]}
        >
          <View style={styles.transcriptContent}>
            {userText ? (
              <View style={styles.userMessage}>
                <Text style={styles.userLabel}>🎤</Text>
                <Text style={styles.userText}>{userText}</Text>
              </View>
            ) : null}

            {aiText ? (
              <View style={styles.aiMessage}>
                <Text style={styles.aiLabel}>🤖</Text>
                <Text style={styles.aiText}>{aiText}</Text>
              </View>
            ) : null}

            {isProcessing && !aiText ? (
              <View style={styles.processingIndicator}>
                <Loader2 size={20} color="#007AFF" />
                <Text style={styles.processingText}>
                  {t("voice.thinking", "思考中...")}
                </Text>
              </View>
            ) : null}
          </View>

          {/* 关闭按钮 */}
          <TouchableOpacity style={styles.closeButton} onPress={handleClose}>
            <Text style={styles.closeButtonText}>✕</Text>
          </TouchableOpacity>
        </Animated.View>
      )}

      {/* 主按钮 */}
      <View style={styles.buttonContainer}>
        <Animated.View
          style={[
            styles.pulseRing,
            {
              transform: [{ scale: pulseAnim }],
              opacity: isRecording
                ? pulseAnim.interpolate({
                    inputRange: [1, 1.3],
                    outputRange: [0.5, 0],
                  })
                : 0,
            },
          ]}
        />

        <TouchableOpacity
          style={[
            styles.mainButton,
            isRecording && styles.recordingButton,
            isProcessing && styles.processingButton,
            isAiSpeaking && styles.speakingButton,
          ]}
          onPressIn={handlePressIn}
          onPressOut={handlePressOut}
          onLongPress={handleLongPress}
          delayLongPress={500}
          activeOpacity={0.8}
        >
          {isProcessing ? (
            <Loader2 size={32} color="white" />
          ) : isRecording ? (
            <Square size={32} color="white" fill="white" />
          ) : (
            <Mic size={32} color="white" />
          )}
        </TouchableOpacity>

        <Text style={styles.buttonText}>{getButtonText()}</Text>

        {isAiSpeaking ? (
          <Text style={styles.hintText}>
            {t("voice.longPressToInterrupt", "长按打断")}
          </Text>
        ) : null}
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    justifyContent: "flex-end",
    paddingBottom: 40,
  },
  transcriptContainer: {
    position: "absolute",
    bottom: 180,
    left: 20,
    right: 20,
    backgroundColor: "rgba(255, 255, 255, 0.95)",
    borderRadius: 16,
    padding: 16,
    maxHeight: 250,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 5,
  },
  transcriptContent: {
    gap: 12,
  },
  userMessage: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
  },
  userLabel: {
    fontSize: 16,
  },
  userText: {
    flex: 1,
    fontSize: 15,
    color: "#333",
    lineHeight: 22,
  },
  aiMessage: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
  },
  aiLabel: {
    fontSize: 16,
  },
  aiText: {
    flex: 1,
    fontSize: 15,
    color: "#666",
    lineHeight: 22,
  },
  processingIndicator: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    justifyContent: "center",
    paddingVertical: 8,
  },
  processingText: {
    fontSize: 14,
    color: "#007AFF",
  },
  closeButton: {
    position: "absolute",
    top: 8,
    right: 8,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: "rgba(0,0,0,0.1)",
    alignItems: "center",
    justifyContent: "center",
  },
  closeButtonText: {
    fontSize: 14,
    color: "#666",
    fontWeight: "bold",
  },
  buttonContainer: {
    alignItems: "center",
    gap: 12,
  },
  pulseRing: {
    position: "absolute",
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: "#FF3B30",
  },
  mainButton: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: "#007AFF",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#007AFF",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  recordingButton: {
    backgroundColor: "#FF3B30",
    shadowColor: "#FF3B30",
  },
  processingButton: {
    backgroundColor: "#FF9500",
    shadowColor: "#FF9500",
  },
  speakingButton: {
    backgroundColor: "#34C759",
    shadowColor: "#34C759",
  },
  buttonText: {
    fontSize: 14,
    color: "#666",
    marginTop: 8,
  },
  hintText: {
    fontSize: 12,
    color: "#999",
  },
})

export default VoiceChatButton
