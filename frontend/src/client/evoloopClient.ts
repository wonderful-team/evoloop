import axios, { type AxiosRequestConfig } from 'axios';
import { fetch } from '@tauri-apps/plugin-http';
import { isTauri } from '@tauri-apps/api/core';

// Niushop Base URL (Hardcoded for now as per plan, or use env)
export const NIUSHOP_BASE_URL = import.meta.env.VITE_NIUSHOP_API_URL || "https://mall.imagicbox.cn";

const tauriAdapter = async (config: AxiosRequestConfig) => {
    let url = config.url;
    if (url && !url.startsWith('http') && config.baseURL) {
        url = `${config.baseURL.replace(/\/$/, '')}/${url.replace(/^\//, '')}`;
    }

    // Serialize params if they exist
    if (config.params) {
        const params = new URLSearchParams();
        for (const key in config.params) {
            if (config.params[key] !== undefined && config.params[key] !== null) {
                params.append(key, config.params[key]);
            }
        }
        const queryString = params.toString();
        if (queryString) {
            url += (url!.includes('?') ? '&' : '?') + queryString;
        }
    }

    try {
        console.log(`[TauriAdapter] Requesting: ${url}`);

        const body = (config.data && typeof config.data === 'object') ? JSON.stringify(config.data) : config.data;
        const response = await fetch(url!, {
            method: config.method?.toUpperCase(),
            headers: config.headers as any,
            body
        });

        const responseData = await response.text();
        console.log(`[TauriAdapter] Response Body: ${responseData.substring(0, 500)}`);

        let data;
        try {
            data = JSON.parse(responseData);
        } catch {
            data = responseData;
        }

        return {
            data,
            status: response.status,
            statusText: response.statusText,
            headers: {},
            config,
            request: {}
        };
    } catch (e) {
        console.error(`[TauriAdapter] Fetch Error:`, e);
        throw e;
    }
};

const evoloopClient = axios.create({
    baseURL: NIUSHOP_BASE_URL,
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
    },
    adapter: isTauri() ? (tauriAdapter as any) : undefined,
});

// Request interceptor to add token
evoloopClient.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('evoloop_token');
        if (token) {
            // Niushop backend checks Input('token'), so passed as query param
            if (!config.params) config.params = {};
            config.params['token'] = token;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Response interceptor
evoloopClient.interceptors.response.use(
    (response) => {
        const res = response.data;
        // Niushop usually returns { code: 0, data: ..., message: ... }
        if (res.code && res.code < 0) {
            return Promise.reject(new Error(res.message || 'Error'));
        }
        return res;
    },
    (error) => {
        return Promise.reject(error);
    }
);

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

export const EvoLoopApi = {
    // Login to Niushop to get token
    login: async (username: string, password: string): Promise<{ token: string, member_id: number }> => {
        const response = await evoloopClient.post('/api/login/login', { username, password });
        return response.data;
    },

    // Mobile SMS Login
    sendMobileCode: async (mobile: string, captcha_id?: string, captcha_code?: string): Promise<{ key: string }> => {
        const data: any = { mobile };
        if (captcha_id && captcha_code) {
            data.captcha_id = captcha_id;
            data.captcha_code = captcha_code;
        }
        const response = await evoloopClient.post('/api/login/mobileCode', data);
        return response.data;
    },

    loginMobile: async (mobile: string, key: string, code: string): Promise<{ token: string, member_id: number }> => {
        const response = await evoloopClient.post('/api/login/mobile', { mobile, key, code });
        return response.data;
    },

    // Captcha
    getCaptcha: async (captcha_id: string = ''): Promise<{ id: string, img: string }> => {
        const response = await evoloopClient.post('/api/captcha/captcha', { captcha_id });
        return response.data;
    },

    getCaptchaConfig: async (): Promise<any> => {
        const response = await evoloopClient.get('/api/config/getCaptchaConfig');
        return response.data?.shop_reception_login; // Returns 1 or 0
    },

    logout: () => {
        // Clear local storage token
        localStorage.removeItem('evoloop_token');
    },

    // Password Recovery
    checkMobile: async (mobile: string): Promise<boolean> => {
        // Returns code: 0 if NOT exists?
        // find.vue says: if res.code == 0 title='Phone not registered'.
        // So code < 0 means error? code == 0 usually means success, but here maybe 'User not found' is 0?
        // Wait. find.vue: if (res.code == 0) { showToast('Not registered'); return false; }
        // This implies code!=0 (likely 1 or similar) means "Exists".
        // Niushop usually: code > 0 or code == 0 is success. 
        // Let's assume endpoint returns whether it exists.
        // If the API returns success(data), check data?
        // Let's implement wrapper and let UI handle logic based on response.
        const response = await evoloopClient.post('/api/member/checkmobile', { mobile });
        // The legacy code treats 'code == 0' as "Mobile NOT registered" (failure for recovery).
        // So for recovery, we want code != 0? Or maybe code < 0 is error, code >= 0 is success (request worked).
        // Inside data: exist?
        // But legacy code checks res.code directly.
        // Standard Niushop: success() returns code=0 usually?
        // If checkmobile returns "User exists", maybe code=1?
        return response as any; // Return full response for logic
    },

    sendFindPasswordCode: async (mobile: string, captcha_id: string, captcha_code: string): Promise<{ key: string }> => {
        const response = await evoloopClient.post('/api/findpassword/mobilecode', {
            mobile,
            captcha_id,
            captcha_code
        });
        return response.data;
    },

    resetPasswordMobile: async (mobile: string, code: string, key: string, password: string): Promise<any> => {
        const response = await evoloopClient.post('/api/findpassword/mobile', {
            mobile,
            code,
            key,
            password
        });
        return response;
    },

    // Registration
    getRegisterConfig: async (): Promise<any> => {
        const response = await evoloopClient.get('/api/register/config');
        return response.data?.value;
    },

    getRegisterAgreement: async (): Promise<any> => {
        const response = await evoloopClient.get('/api/register/aggrement');
        return response.data;
    },

    sendRegisterMobileCode: async (mobile: string, captcha_id?: string, captcha_code?: string): Promise<{ key: string }> => {
        const data: any = { mobile };
        if (captcha_id && captcha_code) {
            data.captcha_id = captcha_id;
            data.captcha_code = captcha_code;
        }
        const response = await evoloopClient.post('/api/register/mobileCode', data);
        return response.data;
    },

    registerMobile: async (data: any): Promise<{ token: string, member_id: number }> => {
        const response = await evoloopClient.post('/api/register/mobile', data);
        return response.data;
    },

    registerUsername: async (data: any): Promise<{ token: string, member_id: number }> => {
        const response = await evoloopClient.post('/api/register/username', data);
        return response.data;
    },

    // EvoLoop Link Plugin APIs
    getDeviceList: async (): Promise<Device[]> => {
        const response = await evoloopClient.get('/evolooplink/api/device/list');
        return response.data; // Assuming response.data is the list, or response.data.list
    },

    bindMobile: async (client_id: string): Promise<{ uid: string }> => {
        const response = await evoloopClient.post('/evolooplink/api/device/bindMobile', { client_id });
        return response.data;
    },

    sendCommand: async (device_id: number, content: string, project_id?: number): Promise<any> => {
        const payload: any = {
            device_id,
            content: { text: content } // Wrap in expected format
        };
        if (project_id) {
            payload.project_id = project_id;
        }
        const response = await evoloopClient.post('/evolooplink/api/command/send', payload);
        return response.data;
    },

    uploadFile: async (file: File): Promise<string> => {
        const formData = new FormData();
        formData.append('file', file);

        // This endpoint returns { code: 0, data: { path: "https://..." } }
        // We use 'chatfile' endpoint we just created in Member Center
        const response = await evoloopClient.post('/api/upload/chatfile', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            }
        });

        // Return full URL
        if (response.data && response.data.path) {
            // If path is relative, prepend base url. But fileCloud usually returns full cloud URL or local relative path.
            // If local relative, we need to prepend domain. 
            // However, Upload.php usually returns storage path.
            // Let's assume we need to handle it.
            let path = response.data.path;
            if (!path.startsWith('http')) {
                // If it's a local upload, prepend API_BASE or similar.
                // But NIUSHOP_BASE_URL is defined.
                // Let's use get_file_url helper logic if available, or just prepend.
                if (path.startsWith('/')) {
                    path = NIUSHOP_BASE_URL + path;
                } else {
                    path = NIUSHOP_BASE_URL + '/' + path;
                }
            }
            return path;
        }
        throw new Error("Upload failed, no path returned");
    },

    // Status check (Optional)
    ping: async () => {
        try {
            await evoloopClient.get('/api/index/index');
            return true;
        } catch {
            return false;
        }
    },

    getRecentLogs: async (device_id: number, limit: number = 50, project_id?: number): Promise<any[]> => {
        const params: any = { device_id, limit };
        if (project_id) {
            params.project_id = project_id;
        }
        const response = await evoloopClient.get('/evolooplink/api/log/recent', {
            params
        });
        return response.data;
    },

    searchLogs: async (keyword: string, device_id?: number, project_id?: number, limit: number = 20): Promise<any[]> => {
        const params: any = { keyword, limit };
        if (device_id) params.device_id = device_id;
        if (project_id) params.project_id = project_id;
        const response = await evoloopClient.get('/evolooplink/api/log/search', { params });
        return response.data.data;
    },

    getContextLogs: async (device_id: number, target_log_id: number): Promise<any[]> => {
        const response = await evoloopClient.get('/evolooplink/api/log/context', {
            params: { device_id, target_log_id }
        });
        return response.data.data;
    },

    // Cloud Project Management
    getCloudProjects: async (params?: { page?: number, page_size?: number, status?: number }): Promise<any> => {
        const response = await evoloopClient.get('/projectmanage/api/project/lists', { params });
        return response.data;
    },

    switchCloudProject: async (project_id: number): Promise<any> => {
        const response = await evoloopClient.post('/projectmanage/api/project/switchProject', { project_id });
        return response.data;
    },

    getCloudCurrentProject: async (): Promise<any> => {
        const response = await evoloopClient.get('/projectmanage/api/project/getCurrentProject');
        return response.data;
    }
};

export default evoloopClient;
