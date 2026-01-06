import { request as __request } from "./core/request";
import { OpenAPI } from "./core/OpenAPI";

export interface ConversationListItem {
    thread_id: string;
    title: string;
    project_id?: number;
    updated_at?: string;
    status: string;
}

export interface MessageItem {
    id: string;
    type: 'human' | 'ai' | 'tool' | 'system';
    content: string;
    thinking?: string;
    created_at?: string;
}

export interface SearchResult {
    thread_id: string;
    role: string;
    content: string;
    created_at: string;
    match_snippet?: string;
}

export class ConversationsService {
    /**
     * List conversations
     */
    public static listConversations(projectId?: number): Promise<ConversationListItem[]> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/conversations',
            query: {
                project_id: projectId
            }
        });
    }

    /**
     * Get conversation messages (History)
     */
    public static getConversationMessages(threadId: string): Promise<MessageItem[]> {
        return __request(OpenAPI, {
            method: 'GET',
            url: `/api/v1/conversations/${threadId}/messages`
        });
    }

    /**
     * Get conversation activity
     */
    public static getConversationActivity(threadId: string): Promise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: `/api/v1/conversations/${threadId}/activity`
        });
    }

    /**
     * Rename conversation
     */
    public static renameConversation(threadId: string, title: string): Promise<{ status: string, thread_id: string, title: string }> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: `/api/v1/conversations/${threadId}`,
            body: { title }
        });
    }

    /**
     * Delete conversation
     */
    public static deleteConversation(threadId: string): Promise<{ status: string, thread_id: string }> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: `/api/v1/conversations/${threadId}`
        });
    }

    /**
     * Search conversations
     */
    public static searchConversations(q: string, projectId?: number): Promise<SearchResult[]> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/conversations/search',
            query: {
                q: q,
                project_id: projectId
            }
        });
    }

    /**
     * Rewind conversation (Undo last turn)
     */
    public static rewindConversation(threadId: string): Promise<{ status: string, removed_count: number }> {
        return __request(OpenAPI, {
            method: 'POST',
            url: `/api/v1/conversations/${threadId}/rewind`
        });
    }
}
