/**
 * LLM Platform Service - 管理模型选择和配置
 *
 * 功能:
 * - 获取可用模型列表 (平台模型 + 自定义模型)
 * - 管理用户选择的模型
 * - 持久化用户选择到 localStorage
 */

import i18n from "@evoloop/shared/i18n"
import {toast} from "sonner"
import {SystemService} from "@/client"

export interface LLMModel {
  id: string
  name: string
  model: string
  type: "platform" | "custom"
  provider?: string
  provider_type?: string
  vision_model?: string | null
  description?: string
  icon?: string
  available?: boolean
  quota_required?: boolean
  supports_streaming?: boolean
  supports_vision?: boolean
  supports_functions?: boolean
  supports_image_generation?: boolean
  supports_video_generation?: boolean
  context_window?: number
  capabilities?: string[]
}

const STORAGE_KEY = "evoloop_selected_model"

class LLMPlatformService {
  private models: LLMModel[] = []
  private selectedModel: string | null = null
  private lastFetchTime = 0
  private readonly CACHE_TTL = 5 * 60 * 1000 // 5 minutes
  private fetchPromise: Promise<LLMModel[]> | null = null // 请求去重锁

  constructor() {
    // 从 localStorage 恢复用户选择
    this.selectedModel = localStorage.getItem(STORAGE_KEY)
  }

  /**
   * 获取可用模型列表
   * 整合平台模型 + 自定义模型 + 本地发现模型（LM Studio/Ollama/GGUF）
   * 后端返回所有模型 (platform + custom)，前端按需过滤显示
   */
  async fetchModels(): Promise<LLMModel[]> {
    // 检查缓存
    const now = Date.now()
    if (this.models.length > 0 && now - this.lastFetchTime < this.CACHE_TTL) {
      return this.models
    }

    // 请求去重：如果已有请求在进行中，复用该 Promise
    if (this.fetchPromise) {
      return this.fetchPromise
    }

    // 创建新的请求
    this.fetchPromise = (async () => {
      try {
        const [response, discovery] = await Promise.all([
          SystemService.getLlmModels(),
          SystemService.discoverModels().catch(() => ({ models: [] })),
        ])
        const data = response as any

        if (data?.models) {
          this.models = data.models as LLMModel[]

          // 合并本地发现模型（LM Studio/Ollama/GGUF），按 id 去重
          const discovered = ((discovery as any)?.models || []) as Array<{
            id: string
            name: string
            model_name: string
            source: string
            status: string
            context_window?: number
            capabilities?: string[]
          }>
          for (const dm of discovered) {
            if (!this.models.some((e) => e.id === dm.id)) {
              this.models.push({
                id: dm.id,
                name: dm.name,
                model: dm.model_name,
                type: "platform",
                provider: dm.source,
                description: "",
                available: dm.status === "available",
                context_window: dm.context_window,
                capabilities: dm.capabilities,
              })
            }
          }

          this.lastFetchTime = now

          // 如果当前选择的模型不在列表中，清除选择
          if (
            this.selectedModel &&
            !this.models.find((m) => m.id === this.selectedModel)
          ) {
            this.selectedModel = null
            localStorage.removeItem(STORAGE_KEY)
          }

          return this.models
        }
        return []
      } catch (error) {
        console.error("[LLMPlatform] Failed to fetch models:", error)
        toast.error(i18n.t("chat.modelSelector.fetchFailed"))
        return []
      } finally {
        // 清除请求锁
        this.fetchPromise = null
      }
    })()

    return this.fetchPromise
  }

  /**
   * 获取缓存的模型列表 (不触发网络请求)
   */
  getCachedModels(): LLMModel[] {
    return this.models
  }

  /**
   * 获取当前选择的模型
   */
  getSelectedModel(): string | null {
    return this.selectedModel
  }

  /**
   * 设置当前选择的模型
   */
  setSelectedModel(modelId: string | null): void {
    this.selectedModel = modelId
    if (modelId) {
      localStorage.setItem(STORAGE_KEY, modelId)
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }

  /**
   * 获取模型详情
   */
  getModelById(modelId: string): LLMModel | undefined {
    return this.models.find((m) => m.id === modelId)
  }

  /**
   * 获取平台模型列表 (需要配额的)
   */
  getPlatformModels(): LLMModel[] {
    return this.models.filter((m) => m.type === "platform")
  }

  /**
   * 获取自定义模型列表 (用户自己的 API Key)
   */
  getCustomModels(): LLMModel[] {
    return this.models.filter((m) => m.type === "custom")
  }

  /**
   * 清除缓存
   */
  clearCache(): void {
    this.models = []
    this.lastFetchTime = 0
  }
}

export const llmPlatformService = new LLMPlatformService()
