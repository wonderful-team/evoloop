
import { cn } from "@evoloop/shared/lib/utils"
import { Brain, Compass, Lightbulb, Zap } from "lucide-react"
import { motion } from "framer-motion"

export interface AgentThought {
    id: string
    type: "thought"
    thought_type: "intent" | "skill_match" | "optimization" | "generic"
    title: string
    content: string | Record<string, any>
    confidence?: number
    timestamp: number
}

interface ThoughtCardProps {
    thought: AgentThought
}

export function ThoughtCard({ thought }: ThoughtCardProps) {
    const getIcon = () => {
        switch (thought.thought_type) {
            case "intent":
                return <Compass className="h-4 w-4 text-blue-500" />
            case "skill_match":
                return <Zap className="h-4 w-4 text-amber-500" />
            case "optimization":
                return <Lightbulb className="h-4 w-4 text-green-500" />
            default:
                return <Brain className="h-4 w-4 text-purple-500" />
        }
    }

    const getBorderColor = () => {
        switch (thought.thought_type) {
            case "intent":
                return "border-blue-500/20 bg-blue-500/5"
            case "skill_match":
                return "border-amber-500/20 bg-amber-500/5"
            case "optimization":
                return "border-green-500/20 bg-green-500/5"
            default:
                return "border-purple-500/20 bg-purple-500/5"
        }
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            className={cn(
                "rounded-md border p-3 mb-2 text-xs",
                getBorderColor()
            )}
        >
            <div className="flex items-center gap-2 mb-1.5 font-medium text-foreground/80">
                {getIcon()}
                <span>{thought.title}</span>
                {thought.confidence && (
                    <span className="ml-auto text-[10px] opacity-70">
                        {Math.round(thought.confidence * 100)}%
                    </span>
                )}
            </div>

            <div className="pl-6 space-y-1">
                {typeof thought.content === "string" ? (
                    <p className="opacity-80">{thought.content}</p>
                ) : (
                    <div className="grid grid-cols-1 gap-1">
                        {Object.entries(thought.content).map(([k, v]) => {
                            if (k === 'type' || k === 'thought_type') return null;
                            return (
                                <div key={k} className="flex gap-2">
                                    <span className="opacity-50 min-w-[60px]">{k}:</span>
                                    <span className="font-mono opacity-90 truncate max-w-[180px]">
                                        {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                    </span>
                                </div>
                            )
                        })}
                    </div>
                )}
            </div>
        </motion.div>
    )
}
