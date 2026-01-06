import type { CancelablePromise } from './core/CancelablePromise';
import { OpenAPI } from './core/OpenAPI';
import { request as __request } from './core/request';

export class ToolsService {
    /**
     * List Runtime Tools
     * @returns unknown[] Successful Response
     * @throws ApiError
     */
    public static listRuntimeTools(): CancelablePromise<Array<any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/tools/runtime',
        });
    }

    /**
     * List All Tools
     * @returns unknown[] Successful Response
     * @throws ApiError
     */
    public static listAllTools(): CancelablePromise<Array<any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/tools',
        });
    }
}
