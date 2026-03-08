import { OpenAPI } from "../client/core/OpenAPI";
import { request as __request } from "../client/core/request";
import type { CancelablePromise } from "../client/core/CancelablePromise";

export interface AndroidDevice {
    serial: string;
    status: string;
    info: string;
}

export interface MirrorDevicesResponse {
    devices: AndroidDevice[];
    scrcpy_available: boolean;
}

export interface StartMirrorResponse {
    success: boolean;
    session_id: string;
    device_id: string;
}

export interface StopMirrorResponse {
    success: boolean;
    message: string;
    video_path: string;
    session_id: string;
    event_count: number;
}

export class MirrorService {
    /**
     * List connected Android devices for mirroring.
     */
    public static listDevices(): CancelablePromise<MirrorDevicesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/learning/mirror/devices',
        });
    }

    /**
     * Start a scrcpy mirroring session.
     */
    public static startMirror(deviceId: string): CancelablePromise<StartMirrorResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/learning/mirror/start',
            body: { device_id: deviceId },
            mediaType: 'application/json',
        });
    }

    /**
     * Stop an active mirroring session.
     */
    public static stopMirror(sessionId: string): CancelablePromise<StopMirrorResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/learning/mirror/stop',
            body: { session_id: sessionId },
            mediaType: 'application/json',
        });
    }

    /**
     * Persist Android mirror events to backend (delayed persistence).
     */
    public static persistEvents(sessionId: string): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/learning/mirror/events',
            body: { session_id: sessionId },
            mediaType: 'application/json',
        });
    }
}
