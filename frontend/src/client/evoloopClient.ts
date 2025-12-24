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
        // ... (lines 118-123)
        const response = await evoloopClient.post('/api/login/login', { username, password });
        return response.data;
    },

    logout: () => {
        // Clear local storage token
        localStorage.removeItem('evoloop_token');
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
