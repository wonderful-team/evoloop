import { EmbeddingSettings } from "./EmbeddingSettings"
import { LLMSettings } from "./LLMSettings"

export function ModelSettings() {
  return (
    <div className="space-y-6">
      <LLMSettings />
      <EmbeddingSettings />
    </div>
  )
}
