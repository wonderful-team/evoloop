import { LLMSettings } from "./LLMSettings"
import { EmbeddingSettings } from "./EmbeddingSettings"

export function ModelSettings() {
    return (
        <div className="space-y-6">
            <LLMSettings />
            <EmbeddingSettings />
        </div>
    )
}
