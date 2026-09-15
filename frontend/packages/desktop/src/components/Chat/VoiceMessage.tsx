import { cn } from "@evoloop/shared/lib/utils"
import { Pause, Play } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { formatDuration } from "@/utils/voiceStorage"

interface VoiceMessageProps {
  audioUrl: string
  duration: number
  waveform?: number[]
  isUser?: boolean
  transcript?: string
  className?: string
}

export function VoiceMessage({
  audioUrl,
  duration,
  waveform = [],
  isUser = false,
  transcript,
  className,
}: VoiceMessageProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [isLoaded, setIsLoaded] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // 生成默认波形（如果没有提供）
  const displayWaveform =
    waveform.length > 0
      ? waveform
      : Array.from({ length: 30 }, () => 0.3 + Math.random() * 0.4)

  useEffect(() => {
    const audio = new Audio(audioUrl)
    audioRef.current = audio

    audio.addEventListener("loadedmetadata", () => {
      setIsLoaded(true)
    })

    audio.addEventListener("ended", () => {
      setIsPlaying(false)
      setCurrentTime(0)
    })

    audio.addEventListener("error", () => {
      console.error("Failed to load audio:", audioUrl)
      setIsLoaded(false)
    })

    return () => {
      audio.pause()
      audio.src = ""
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current)
      }
    }
  }, [audioUrl])

  // 更新进度
  useEffect(() => {
    if (isPlaying) {
      progressIntervalRef.current = setInterval(() => {
        if (audioRef.current) {
          setCurrentTime(audioRef.current.currentTime)
        }
      }, 100)
    } else {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current)
      }
    }

    return () => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current)
      }
    }
  }, [isPlaying])

  const togglePlay = useCallback(() => {
    if (!audioRef.current || !isLoaded) return

    if (isPlaying) {
      audioRef.current.pause()
      setIsPlaying(false)
    } else {
      audioRef.current.play().catch((err) => {
        console.error("Failed to play audio:", err)
      })
      setIsPlaying(true)
    }
  }, [isPlaying, isLoaded])

  const remainingTime = Math.max(0, duration - currentTime)

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      {/* 语音消息主体 */}
      <div
        className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-2xl min-w-[180px] max-w-[300px] cursor-pointer",
          "transition-all duration-200",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-amber-500/10 border border-amber-500/20",
        )}
        onClick={togglePlay}
      >
        {/* 播放/暂停按钮 */}
        <button
          type="button"
          className={cn(
            "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
            "transition-colors",
            isUser
              ? "bg-white/20 hover:bg-white/30"
              : "bg-amber-500/20 hover:bg-amber-500/30",
          )}
          onClick={(e) => {
            e.stopPropagation()
            togglePlay()
          }}
        >
          {isPlaying ? (
            <Pause
              className={cn(
                "w-4 h-4",
                isUser ? "text-white" : "text-amber-700 dark:text-amber-300",
              )}
            />
          ) : (
            <Play
              className={cn(
                "w-4 h-4 ml-0.5",
                isUser ? "text-white" : "text-amber-700 dark:text-amber-300",
              )}
            />
          )}
        </button>

        {/* 波形 */}
        <div className="flex-1 flex items-center gap-[2px] h-6 px-1">
          {displayWaveform.map((amplitude, index) => {
            // 计算当前进度对应的波形索引
            const waveIndex = Math.floor(
              (index / displayWaveform.length) * duration,
            )
            const isPlayed = currentTime >= waveIndex

            return (
              <div
                key={index}
                className={cn(
                  "w-[3px] rounded-full transition-all duration-150",
                  isUser
                    ? isPlayed
                      ? "bg-white"
                      : "bg-white/40"
                    : isPlayed
                      ? "bg-amber-600 dark:bg-amber-400"
                      : "bg-amber-400/40 dark:bg-amber-600/40",
                )}
                style={{
                  height: `${Math.max(20, amplitude * 100)}%`,
                  opacity: isPlaying ? 1 : 0.7,
                }}
              />
            )
          })}
        </div>

        {/* 时长 */}
        <span
          className={cn(
            "text-xs font-medium flex-shrink-0",
            isUser ? "text-white/80" : "text-amber-700 dark:text-amber-300",
          )}
        >
          {isPlaying
            ? formatDuration(Math.floor(remainingTime))
            : formatDuration(duration)}
        </span>
      </div>

      {/* 转文字内容（如果有） */}
      {transcript && (
        <div
          className={cn(
            "text-sm px-3 py-1.5 rounded-lg max-w-[300px]",
            isUser
              ? "bg-primary/10 text-primary-foreground/80"
              : "bg-muted text-muted-foreground",
          )}
        >
          {transcript}
        </div>
      )}
    </div>
  )
}

/**
 * 简化版语音消息（仅显示时长和播放按钮）
 */
export function VoiceMessageSimple({
  audioUrl,
  duration,
  isUser = false,
}: Omit<VoiceMessageProps, "waveform" | "transcript">) {
  const [isPlaying, setIsPlaying] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    const audio = new Audio(audioUrl)
    audioRef.current = audio

    audio.addEventListener("ended", () => setIsPlaying(false))
    audio.addEventListener("pause", () => setIsPlaying(false))

    return () => {
      audio.pause()
      audio.src = ""
    }
  }, [audioUrl])

  const togglePlay = () => {
    if (!audioRef.current) return

    if (isPlaying) {
      audioRef.current.pause()
    } else {
      audioRef.current.play()
    }
    setIsPlaying(!isPlaying)
  }

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 px-3 py-2 rounded-2xl cursor-pointer",
        "transition-colors",
        isUser
          ? "bg-primary text-primary-foreground"
          : "bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-300",
      )}
      onClick={togglePlay}
    >
      {isPlaying ? (
        <Pause className="w-4 h-4" />
      ) : (
        <Play className="w-4 h-4 ml-0.5" />
      )}
      <span className="text-sm font-medium">{formatDuration(duration)}</span>
    </div>
  )
}
