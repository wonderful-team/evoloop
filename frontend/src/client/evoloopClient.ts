
import { OpenAPI } from "./core/OpenAPI";
import { request as __request } from "./core/request";
import { adaptedAxios } from "./core/adaptedAxios";

// Niushop Configuration
const NIUSHOP_BASE_URL = import.meta.env.VITE_NIUSHOP_API_URL || "https://mall.imagicbox.cn";
// Create a separate config for Niushop to avoid interfering with global OpenAPI config
const NiushopConfig = { ...OpenAPI, BASE: NIUSHOP_BASE_URL };

// Helper to inject adapted axios
const requestWithAdapter = async <T>(config: any, options: any): Promise<T> => {
    return await __request(config, options, adaptedAxios);
};

// --- Types ---
export interface NiushopResponse<T = any> {
    code: number;
    message: string;
    data: T;
    [key: string]: any;
}

export interface Device {
    device_id: number;
    site_id: number;
    member_id: number;
    device_name: string;
    device_key: string;
    status: number; // 0 offline, 1 online
    client_id: string;
    last_heartbeat: number;
    create_time: number;
    os_info: string;
}

export interface LoginResponse {
    token: string;
    member_id: number;
}

export interface MobileVerifyResponse {
    key: string;
}

// --- API Class ---
export class EvoLoopApi {
    // --- Login & Auth ---

    static async login(username: string, password: string): Promise<LoginResponse> {
        const res = await requestWithAdapter<NiushopResponse<LoginResponse>>(NiushopConfig, {
            method: 'POST',
            url: '/api/login/login',
            body: { username, password }
        });
        return res.data;
    }

    static async loginMobile(mobile: string, key: string, code: string): Promise<LoginResponse> {
        const res = await requestWithAdapter<NiushopResponse<LoginResponse>>(NiushopConfig, {
            method: 'POST',
            url: '/api/login/mobile',
            body: { mobile, key, code }
        });
        return res.data;
    }

    static async sendMobileCode(mobile: string, captchaId?: string, vercode?: string): Promise<MobileVerifyResponse> {
        const body: any = { mobile };
        if (captchaId && vercode) {
            body.captcha_id = captchaId;
            body.captcha_code = vercode;
        }
        const res = await requestWithAdapter<NiushopResponse<MobileVerifyResponse>>(NiushopConfig, {
            method: 'POST',
            url: '/api/login/mobileCode',
            body
        });
        return res.data;
    }

    static async getCaptchaConfig(): Promise<number> {
        const res = await requestWithAdapter<NiushopResponse<{ shop_reception_login: number }>>(NiushopConfig, {
            method: 'GET',
            url: '/api/config/getCaptchaConfig',
        });
        // Returns 1 or 0 usually, wrapped in shop_reception_login inside data?
        // evoloopClient.ts says: res.shop_reception_login.
        // Wait, evoloopClient_new.ts originally did: return res?.shop_reception_login.
        // Let's assume the root response has it or data has it.
        // Niushop general config API: might return { code: 0, data: { value: ... } } or similar.
        // Based on original new file: res?.shop_reception_login.
        // Let's return the whole data object just in case or trace carefully.
        // Safe bet: return res.data?.shop_reception_login ?? res.shop_reception_login;
        return res.data?.shop_reception_login ?? (res as any).shop_reception_login;
    }

    static async getCaptcha(captchaId?: string): Promise<{ id: string, img: string }> {
        const res = await requestWithAdapter<NiushopResponse<{ id: string, img: string }>>(NiushopConfig, {
            method: 'POST',
            url: '/api/captcha/captcha',
            body: { captcha_id: captchaId || '' }
        });
        return res.data;
    }

    static async checkMobile(mobile: string): Promise<boolean> {
        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'POST',
            url: '/api/member/checkmobile',
            body: { mobile }
        });
        // API usually returns code > 0 or specific data if exists.
        // We return the raw response-like object or boolean.
        // If we strictly follow types, we should interpret it.
        // Legacy: "return response as any".
        // Let's return boolean based on existence or just the full object for caller flex.
        // But strict is better. If ambiguous, return full response.
        return res as any;
    }

    // --- Password Recovery ---

    static async sendFindPasswordCode(mobile: string, captchaId: string, vercode?: string): Promise<MobileVerifyResponse> {
        const res = await requestWithAdapter<NiushopResponse<MobileVerifyResponse>>(NiushopConfig, {
            method: 'POST',
            url: '/api/findpassword/mobilecode',
            body: { mobile, captcha_id: captchaId, captcha_code: vercode }
        });
        return res.data;
    }

    static async resetPasswordMobile(mobile: string, code: string, key: string, password: string): Promise<any> {
        return await requestWithAdapter(NiushopConfig, {
            method: 'POST',
            url: '/api/findpassword/mobile',
            body: { mobile, code, key, password }
        });
    }

    // --- Registration ---

    static async getRegisterConfig(): Promise<any> {
        const res = await requestWithAdapter<NiushopResponse<{ value: any }>>(NiushopConfig, {
            method: 'GET',
            url: '/api/register/config',
        });
        return res.data?.value;
    }

    static async getRegisterAgreement(): Promise<any> {
        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'GET',
            url: '/api/register/aggrement',
        });
        return res.data;
    }

    static async sendRegisterMobileCode(mobile: string, captchaId?: string, vercode?: string): Promise<MobileVerifyResponse> {
        const body: any = { mobile };
        if (captchaId && vercode) {
            body.captcha_id = captchaId;
            body.captcha_code = vercode;
        }
        const res = await requestWithAdapter<NiushopResponse<MobileVerifyResponse>>(NiushopConfig, {
            method: 'POST',
            url: '/api/register/mobileCode',
            body
        });
        return res.data;
    }

    static async registerMobile(data: any): Promise<LoginResponse> {
        const res = await requestWithAdapter<NiushopResponse<LoginResponse>>(NiushopConfig, {
            method: 'POST',
            url: '/api/register/mobile',
            body: data
        });
        return res.data;
    }

    static async registerUsername(data: any): Promise<LoginResponse> {
        const res = await requestWithAdapter<NiushopResponse<LoginResponse>>(NiushopConfig, {
            method: 'POST',
            url: '/api/register/username',
            body: data
        });
        return res.data;
    }

    // --- EvoLoop Link & Devices ---

    static async getDeviceList(): Promise<Device[]> {
        const res = await requestWithAdapter<NiushopResponse<Device[]>>(NiushopConfig, {
            method: 'GET',
            url: '/evolooplink/api/device/list',
        });
        // Sometimes list APIs return the array directly or in data.
        return Array.isArray(res.data) ? res.data : [];
    }

    static async bindMobile(clientId: string): Promise<{ uid: string }> {
        const res = await requestWithAdapter<NiushopResponse<{ uid: string }>>(NiushopConfig, {
            method: 'POST',
            url: '/evolooplink/api/device/bindMobile',
            body: { client_id: clientId }
        });
        return res.data;
    }

    static async sendCommand(deviceId: number, content: string, projectId?: number): Promise<any> {
        const body: any = {
            device_id: deviceId,
            content: { text: content }
        };
        if (projectId) body.project_id = projectId;

        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'POST',
            url: '/evolooplink/api/command/send',
            body
        });
        return res.data;
    }

    // --- Projects ---

    static async getCloudProjects(params: any): Promise<any> {
        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'GET',
            url: '/projectmanage/api/project/lists',
            query: params
        });
        return res.data;
    }

    static async getCloudCurrentProject(): Promise<any> {
        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'GET',
            url: '/projectmanage/api/project/getCurrentProject',
        });
        return res.data;
    }

    static async switchCloudProject(projectId: number): Promise<any> {
        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'POST',
            url: '/projectmanage/api/project/switchProject',
            body: { project_id: projectId }
        });
        return res.data;
    }

    // --- Config ---

    static async getServicerConfig(): Promise<any> {
        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'GET',
            url: '/api/config/servicer',
        });
        return res.data?.value;
    }

    // --- Member Cancellation (Mobile Direct) ---

    static async getMemberCancellationInfo(): Promise<any> {
        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'GET',
            url: '/membercancel/api/membercancel/info',
        });
        return res.data;
    }

    static async applyMemberCancellation(): Promise<any> {
        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'POST',
            url: '/membercancel/api/membercancel/apply',
        });
        return res;
    }

    static async cancelMemberCancellationApply(): Promise<any> {
        const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
            method: 'POST',
            url: '/membercancel/api/membercancel/cancelApply',
        });
        return res;
    }

    // --- Logs ---

    static async getRecentLogs(deviceId: number, limit: number, projectId?: number): Promise<any[]> {
        const res = await requestWithAdapter<NiushopResponse<any[]>>(NiushopConfig, {
            method: 'GET',
            url: '/evolooplink/api/log/recent',
            query: { device_id: deviceId, limit, project_id: projectId }
        });
        return res.data || [];
    }

    static async searchLogs(q: string, deviceId?: number, projectId?: number, limit?: number): Promise<any[]> {
        const res = await requestWithAdapter<NiushopResponse<{ data: any[] }>>(NiushopConfig, {
            method: 'GET',
            url: '/evolooplink/api/log/search',
            query: { keyword: q, device_id: deviceId, project_id: projectId, limit }
        });
        return res.data?.data || [];
    }

    static async getContextLogs(deviceId: number, highlightId?: string): Promise<any[]> {
        const res = await requestWithAdapter<NiushopResponse<{ data: any[] }>>(NiushopConfig, {
            method: 'GET',
            url: '/evolooplink/api/log/context',
            query: { device_id: deviceId, target_log_id: highlightId }
        });
        return res.data?.data || [];
    }

    // --- File Upload ---

    static async uploadFile(file: File): Promise<string> {
        const formData = { file }; // core/request.ts handles object -> FormData conversion if needed, but lets send raw.
        // core/request converts `options.formData` to FormData.

        const res = await requestWithAdapter<NiushopResponse<{ path: string }>>(NiushopConfig, {
            method: 'POST',
            url: '/api/upload/chatfile',
            formData: formData,
        });

        // Handle path fixup
        let path = res.data?.path || "";
        // Normalize backslashes to slashes
        path = path.replace(/\\/g, '/');

        if (path && !path.startsWith('http')) {
            if (path.startsWith('/')) {
                path = NIUSHOP_BASE_URL + path;
            } else {
                path = NIUSHOP_BASE_URL + '/' + path;
            }
        }
        return path;
    }

    // Stub definition for compatibility if needed
    static logout() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('evoloop_token');
    }
    // --- Cloud AI Classes ---
    // (Defined below EvoLoopApi to allow static reference if needed, or inside)
    static AI = class CloudAI {
        static async getModels(): Promise<AIModel[]> {
            const res = await requestWithAdapter<NiushopResponse<AIModel[]>>(NiushopConfig, {
                method: 'GET',
                url: '/api/AI/models',
            });
            return res.data;
        }

        static async getConversations(page = 1, pageSize = 20): Promise<{ list: AIConversation[], count: number }> {
            const res = await requestWithAdapter<NiushopResponse<{ list: AIConversation[], count: number }>>(NiushopConfig, {
                method: 'GET',
                url: '/api/AI/conversations',
                query: { page, page_size: pageSize }
            });
            return res.data;
        }

        static async getMessages(conversationId: number, page = 1, pageSize = 20): Promise<{ list: AIMessage[], count: number }> {
            const res = await requestWithAdapter<NiushopResponse<{ list: AIMessage[], count: number }>>(NiushopConfig, {
                method: 'GET',
                url: '/api/AI/messages',
                query: { conversation_id: conversationId, page, page_size: pageSize }
            });
            // Backend returns { list, count } inside data based on pagination
            return res.data;
        }

        static async createConversation(_message: string, _model: string): Promise<number> {
            // Implicitly created via chat usually, but if we have explicit endpoint
            // AI.chat handles creation if conversation_id is new/empty.
            return 0;
        }

        static async renameConversation(id: number, title: string): Promise<boolean> {
            const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
                method: 'POST',
                url: '/api/AI/renameConversation',
                body: { conversation_id: id, title }
            });
            return res.code === 0;
        }

        static async deleteConversation(id: number): Promise<boolean> {
            const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
                method: 'POST',
                url: '/api/AI/deleteConversation',
                body: { conversation_id: id }
            });
            return res.code === 0;
        }

        /**
         * Send chat message with optional streaming
         */
        static async chat(
            params: {
                message: string;
                model?: string;
                conversation_id?: number | string;
                stream?: boolean;
                context?: any;
            },
            onStream?: (chunk: string, meta?: any) => void
        ): Promise<any> {
            // If not streaming, use standard adapter
            if (!params.stream) {
                const res = await requestWithAdapter<NiushopResponse>(NiushopConfig, {
                    method: 'POST',
                    url: '/api/AI/chat',
                    body: params
                });
                return res.data;
            }

            // Streaming Implementation
            // We need to use fetch directly to read the stream
            const token = localStorage.getItem('evoloop_token');
            const url = new URL('/api/AI/chat', NIUSHOP_BASE_URL);
            if (token) url.searchParams.append('token', token); // Auth via query param

            // Use Tauri fetch if available (imported via adapter usually, need to ensure access)
            // Or standard fetch. Adapter uses @tauri-apps/plugin-http fetch.
            // We'll trust global fetch or dynamic import if in strict Tauri env without polyfill.
            // Assuming `fetch` is globally patched or available.

            // Note: In Tauri, standard `fetch` might not work with CSP or headers same as plugin-http.
            // But let's try standard fetch first or grab from adapter logic?
            // AdaptedAxios imports fetch from plugin-http. We should allow access.
            const { fetch } = await import('@tauri-apps/plugin-http');

            try {
                const response = await fetch(url.toString(), {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(params)
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                if (!response.body) return;

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });
                    buffer += chunk;

                    const lines = buffer.split('\n');
                    buffer = lines.pop() || ""; // Keep incomplete line

                    for (const line of lines) {
                        if (line.trim() === '') continue;
                        if (line.startsWith('data:')) {
                            const dataStr = line.replace(/^data:\s?/, '').trim();
                            if (dataStr === '[DONE]') return;
                            try {
                                const data = JSON.parse(dataStr);
                                if (onStream) {
                                    // Depending on backend format.
                                    // AI.php usually wraps stream chunks. E.g. { content: "...", ... }
                                    // Need to verify exact emission format from OpenAIService/QwenService.
                                    // Usually it emits `data: JSON`.
                                    const content = data.content !== undefined ? data.content : (data.choices?.[0]?.delta?.content || "");
                                    onStream(content, data);
                                }
                            } catch (e) {
                                console.error('Error parsing stream data', e);
                            }
                        }
                    }
                }
            } catch (e) {
                console.error("Stream fetch failed", e);
                throw e;
            }
        }
    }
}

// --- AI Types ---

export interface AIModel {
    model_type: string;
    name: string;
    capabilities: string[];
    max_tokens: number;
    configured: boolean;
}

export interface AIConversation {
    id: number;
    title: string;
    model: string;
    create_time: number;
    update_time: number;
}

export interface AIMessage {
    id: number;
    conversation_id: number;
    role: 'user' | 'assistant' | 'system';
    content: string;
    create_time: number;
    meta?: any;
}
