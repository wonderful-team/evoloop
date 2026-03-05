/**
 * Timeline - Visual timeline of video with annotations
 */

import { useTranslation } from "react-i18next"
import { cn } from "@evoloop/shared/lib/utils"

interface Annotation {
    video_timestamp_ms: number
    annotation_type: string
}

interface TimelineProps {
    duration: number
    currentTime: number
    annotations: Annotation[]
    onSeek: (timeMs: number) => void
}

export function Timeline({ duration, currentTime, annotations, onSeek }: TimelineProps) {
    const { t } = useTranslation()
    if (duration === 0) return null

    const progress = (currentTime / duration) * 100

    const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
        const rect = e.currentTarget.getBoundingClientRect()
        const clickX = e.clientX - rect.left
        const percentage = clickX / rect.width
        const newTime = percentage * duration
        onSeek(newTime)
    }

    return (
        <div className="relative h-8 bg-muted rounded-lg overflow-hidden cursor-pointer" onClick={handleClick}>
            {/* Progress bar */}
            <div
                className="absolute left-0 top-0 bottom-0 bg-primary/20 transition-all"
                style={{ width: `${progress}%` }}
            />

            {/* Current position indicator */}
            <div
                className="absolute top-0 bottom-0 w-0.5 bg-primary transition-all"
                style={{ left: `${progress}%` }}
            >
                <div className="absolute -top-1 -left-1 w-2.5 h-2.5 rounded-full bg-primary" />
            </div>

            {/* Annotation markers */}
            {annotations.map((ann, idx) => {
                const position = (ann.video_timestamp_ms / duration) * 100
                return (
                    <div
                        key={idx}
                        className={cn(
                            "absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full border-2 border-background",
                            ann.annotation_type === "extract_region"
                                ? "bg-green-500"
                                : ann.annotation_type === "click_point"
                                ? "bg-blue-500"
                                : "bg-yellow-500"
                        )}
                        style={{ left: `${position}%` }}
                        title={t("annotationList.markerTitle", { number: idx + 1, time: formatTime(ann.video_timestamp_ms) })}
                    />
                )
            })}

            {/* Time labels */}
            <div className="absolute bottom-0 left-0 right-0 flex justify-between px-2 text-[10px] text-muted-foreground">
                <span>0:00</span>
                <span>{formatTime(duration)}</span>
            </div>
        </div>
    )
}

function formatTime(ms: number): string {
    const totalSeconds = Math.floor(ms / 1000)
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    return `${minutes}:${seconds.toString().padStart(2, "0")}`
}
