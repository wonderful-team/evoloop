import { request as __request } from "./core/request";
import { OpenAPI } from "./core/OpenAPI";

export interface ProjectResource {
    id: number;
    project_id: number;
    type: 'file' | 'link';
    name: string;
    content: string;
    created_at: string;
}

export interface ResourceCreate {
    type: 'file' | 'link';
    name: string;
    content: string;
}

export class ResourcesService {
    /**
     * List all pinned resources for a project
     */
    public static listResources(projectId: number): Promise<ProjectResource[]> {
        return __request(OpenAPI, {
            method: 'GET',
            url: `/api/v1/projects/${projectId}/resources`
        });
    }

    /**
     * Add a new resource (Pin a file or add a link)
     */
    public static createResource(projectId: number, requestBody: ResourceCreate): Promise<ProjectResource> {
        return __request(OpenAPI, {
            method: 'POST',
            url: `/api/v1/projects/${projectId}/resources`,
            body: requestBody
        });
    }

    /**
     * Remove a resource
     */
    public static deleteResource(projectId: number, resourceId: number): Promise<{ status: string; id: number }> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: `/api/v1/projects/${projectId}/resources/${resourceId}`
        });
    }
}
