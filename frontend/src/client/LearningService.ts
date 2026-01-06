import { request as __request } from "./core/request";
import { OpenAPI } from "./core/OpenAPI";


// Types
export interface HumanInputRequest {
    id: string;
    thread_id: string;
    request_type: "text" | "choice" | "confirmation" | "approval";
    prompt: string;
    options?: string[];
    context?: string;
    default_value?: string;
    created_at: string;
    status: "pending" | "completed" | "timeout" | "cancelled";
}

export interface RespondRequest {
    response: any;
}

export interface RespondResponse {
    success: boolean;
    message: string;
}

export interface RecordedEvent {
    timestamp: number;
    event_type: string;
    target_selector?: string;
    target_text?: string;
    payload?: Record<string, unknown>;
    screenshot_base64?: string;
}

export interface LearnedSkill {
    id: number;
    name: string;
    description: string;
    trigger_patterns: string[];
    parameters?: SkillParameter[];
    steps?: SkillStep[];
    tools_used: string[];
    success_count: number;
    failure_count: number;
    is_active: boolean;
    created_at?: string;
}

export interface SkillParameter {
    name: string;
    type: string;
    description: string;
    required: boolean;
    default?: string;
}

export interface SkillStep {
    action: string;
    args: Record<string, any>;
    condition?: string;
    on_error?: string;
}

// API Class
export class LearningService {

    /**
     * Get all pending human input requests
     */
    public static getPendingRequests(threadId?: string): Promise<HumanInputRequest[]> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/learning/human-requests',
            query: {
                'thread_id': threadId,
            },
        });
    }

    /**
     * Get a specific request by ID
     */
    public static getRequest(requestId: string): Promise<HumanInputRequest> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/learning/human-requests/{request_id}',
            path: {
                'request_id': requestId,
            },
        });
    }

    /**
     * Submit a response to a pending request
     */
    public static respondToRequest(
        requestId: string,
        response: string
    ): Promise<RespondResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/learning/human-requests/{request_id}/respond',
            path: {
                'request_id': requestId,
            },
            body: {
                response: response,
            },
        });
    }

    /**
     * Cancel a pending request
     */
    public static cancelRequest(requestId: string): Promise<RespondResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/learning/human-requests/{request_id}/cancel',
            path: {
                'request_id': requestId,
            },
        });
    }

    /**
     * Cleanup old requests
     */
    public static cleanup(maxAgeHours: number = 24): Promise<RespondResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/learning/cleanup',
            query: {
                'max_age_hours': maxAgeHours,
            },
        });
    }

    // ============ Trace Recording (Phase 1) ============

    /**
     * Start a recording session for imitation learning
     */
    public static startRecording(threadId: string, taskName?: string): Promise<{ session_id: string; message: string }> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/learning/traces/start',
            body: {
                thread_id: threadId,
                task_name: taskName,
            },
        });
    }

    /**
     * Record a batch of UI events
     */
    public static recordEvents(
        sessionId: string,
        threadId: string,
        events: RecordedEvent[]
    ): Promise<RespondResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/learning/traces/events',
            body: {
                session_id: sessionId,
                thread_id: threadId,
                events: events,
            },
        });
    }

    /**
     * Stop a recording session
     */
    public static stopRecording(sessionId: string): Promise<{ session_id: string; event_count: number; message: string }> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/learning/traces/stop',
            query: {
                'session_id': sessionId,
            },
        });
    }

    /**
     * List active recording sessions
     */
    public static listRecordingSessions(threadId?: string): Promise<{
        sessions: Array<{
            session_id: string;
            thread_id: string;
            task_name?: string;
            started_at: string;
            event_count: number;
        }>
    }> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/learning/traces/sessions',
            query: {
                'thread_id': threadId,
            },
        });
    }

    // ============ Skill Management (Phase 2) ============

    /**
     * Synthesize a new skill from a trace sequence
     */
    public static synthesizeSkill(
        threadId: string,
        sessionId?: string
    ): Promise<{
        success: boolean;
        skill_id: number;
        skill_name: string;
        skill_yaml: string;
    }> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/learning/skills/synthesize',
            body: {
                thread_id: threadId,
                session_id: sessionId,
            },
        });
    }

    /**
     * List all learned skills
     */
    public static listSkills(activeOnly: boolean = true): Promise<{
        skills: LearnedSkill[];
    }> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/learning/skills',
            query: {
                'active_only': activeOnly,
            },
        });
    }

    /**
     * Get details of a specific skill
     */
    public static getSkill(skillId: number): Promise<LearnedSkill> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/learning/skills/{skill_id}',
            path: {
                'skill_id': skillId,
            },
        });
    }

    /**
     * Deactivate (delete) a skill
     */
    public static deactivateSkill(skillId: number): Promise<{ success: boolean; message: string }> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/learning/skills/{skill_id}',
            path: {
                'skill_id': skillId,
            },
        });
    }

    /**
     * Execute a skill
     */
    public static executeSkill(
        skillId: number,
        threadId: string,
        params: any,
        projectId?: number
    ): Promise<{ success: boolean; message: string }> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/learning/skills/{skill_id}/execute',
            path: {
                'skill_id': skillId,
            },
            body: {
                thread_id: threadId,
                params: params,
                project_id: projectId
            }
        });
    }
}

