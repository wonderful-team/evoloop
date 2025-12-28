
import axios, { type AxiosRequestConfig } from 'axios';
import { fetch } from '@tauri-apps/plugin-http';
import { isTauri } from '@tauri-apps/api/core';

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

export const adaptedAxios = axios.create({
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
    },
    adapter: isTauri() ? (tauriAdapter as any) : undefined,
});

// Request interceptor to add token
adaptedAxios.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('evoloop_token');
        if (token) {
            // Niushop backend checks Input('token'), so passed as query param
            if (!config.params) config.params = {};
            config.params['token'] = token;
        } else {
            // Guest Mode
            let guestId = localStorage.getItem('evoloop_guest_id');
            if (!guestId) {
                guestId = Math.random().toString(36).substring(2) + Date.now().toString(36);
                localStorage.setItem('evoloop_guest_id', guestId);
            }
            if (!config.headers) config.headers = {} as any;
            config.headers['X-Guest-ID'] = guestId;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Response interceptor
adaptedAxios.interceptors.response.use(
    (response) => {
        const res = response.data;
        // Niushop usually returns { code: 0, data: ..., message: ... }
        // If code < 0, it's an error.
        if (res && typeof res.code === 'number' && res.code < 0) {
            return Promise.reject(new Error(res.message || 'Error'));
        }
        return response; // Return the full response object, core/request.ts expects it (or data?)
        // core/request.ts expects axiosClient.request to return AxiosResponse.
        // And then it calls `getResponseBody(response)`.
        // If we return just data here, `core/request.ts` might break if it tries to access .status.
        // Wait, regular axios interceptors usually return response.
        // Yes, return response.
    },
    (error) => {
        return Promise.reject(error);
    }
);
