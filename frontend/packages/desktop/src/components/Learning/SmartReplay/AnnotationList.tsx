/**
 * AnnotationList - Display and manage list of annotations
 */

import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Trash2, Edit2, Check, MapPin } from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { cn } from "@evoloop/shared/lib/utils"

interface Annotation {
    video_timestamp_ms: number
    annotation_type: string
    region?: {
        x: number
        y: number
        width: number
        height: number
    }
    user_note?: string
}

interface AnnotationListProps {
    annotations: Annotation[]
    activeIndex: number | null
    onSelect: (index: number) => void
    onUpdateNote: (index: number, note: string) => void
    onDelete: (index: number) => void
}

export function AnnotationList({
    annotations,
    activeIndex,
    onSelect,
    onUpdateNote,
    onDelete,
}: AnnotationListProps) {
    const { t } = useTranslation()
    const [editingIndex, setEditingIndex] = useState<number | null>(null)
    const [editValue, setEditValue] = useState("")

    const startEdit = (index: number, currentNote: string = "") => {
        setEditingIndex(index)
        setEditValue(currentNote)
    }

    const saveEdit = (index: number) => {
        onUpdateNote(index, editValue)
        setEditingIndex(null)
    }

    if (annotations.length === 0) {
        return (
            <div className="text-center py-8 text-muted-foreground">
                <MapPin className="mx-auto h-8 w-8 mb-2 opacity-50" />
                <p className="text-sm">{t("annotationList.noAnnotations")}</p>
                <p className="text-xs">{t("annotationList.clickDrawRegion")}</p>
            </div>
        )
    }

    return (
        <div className="space-y-2">
            {annotations.map((ann, idx) => (
                <div
                    key={idx}
                    className={cn(
                        "p-3 rounded-lg border cursor-pointer transition-colors",
                        activeIndex === idx
                            ? "border-primary bg-primary/5"
                            : "border-border hover:border-primary/50"
                    )}
                    onClick={() => onSelect(idx)}
                >
                    <div className="flex items-start gap-2">
                        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center font-medium">
                            {idx + 1}
                        </span>

                        <div className="flex-1 min-w-0">
                            {editingIndex === idx ? (
                                <div className="flex gap-1">
                                    <Input
                                        value={editValue}
                                        onChange={(e) => setEditValue(e.target.value)}
                                        placeholder={t("annotationList.describeRegion")}
                                        className="h-7 text-sm"
                                        autoFocus
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter") saveEdit(idx)
                                            if (e.key === "Escape") setEditingIndex(null)
                                        }}
                                    />
                                    <Button
                                        size="icon"
                                        variant="ghost"
                                        className="h-7 w-7"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            saveEdit(idx)
                                        }}
                                    >
                                        <Check className="h-3 w-3" />
                                    </Button>
                                </div>
                            ) : (
                                <div className="flex items-center gap-1">
                                    <p
                                        className={cn(
                                            "text-sm truncate flex-1",
                                            !ann.user_note && "text-muted-foreground italic"
                                        )}
                                    >
                                        {ann.user_note || t("annotationList.clickToAddDescription")}
                                    </p>
                                    <Button
                                        size="icon"
                                        variant="ghost"
                                        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            startEdit(idx, ann.user_note || "")
                                        }}
                                    >
                                        <Edit2 className="h-3 w-3" />
                                    </Button>
                                </div>
                            )}

                            <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                                <span>{formatTime(ann.video_timestamp_ms)}</span>
                                {ann.region && (
                                    <span>
                                        • {Math.round(ann.region.width)}×{Math.round(ann.region.height)}
                                    </span>
                                )}
                            </div>
                        </div>

                        <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 text-destructive opacity-0 group-hover:opacity-100 hover:bg-destructive/10"
                            onClick={(e) => {
                                e.stopPropagation()
                                onDelete(idx)
                            }}
                        >
                            <Trash2 className="h-3 w-3" />
                        </Button>
                    </div>
                </div>
            ))}
        </div>
    )
}

function formatTime(ms: number): string {
    const totalSeconds = Math.floor(ms / 1000)
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
}
