import { OpenAPI } from "../client/core/OpenAPI";
import { request as __request } from "../client/core/request";
import type { CancelablePromise } from "../client/core/CancelablePromise";

export interface LibraryFile {
    id: number;
    path: string;
    name: string;
    last_indexed_at: string;
    checksum: string;
}

export class LibraryService {
    /**
     * List all files in the global knowledge base.
     */
    public static listFiles(): CancelablePromise<LibraryFile[]> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/library/files',
        });
    }

    /**
     * Upload a file to the global knowledge base.
     */
    public static uploadFile(file: File): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/library/upload',
            formData: {
                file: file,
            },
            mediaType: 'multipart/form-data',
        });
    }

    /**
     * Delete a file from the global knowledge base.
     */
    public static deleteFile(fileId: number): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: `/api/v1/library/files/${fileId}`,
        });
    }
}
