
export enum TaskStatus {
    PENDING = 1,
    IN_PROGRESS = 2,
    COMPLETED = 3,
    ARCHIVED = 4
}

export enum TaskPriority {
    LOW = 1,
    NORMAL = 2,
    HIGH = 3,
    URGENT = 4
}

export interface Task {
    task_id: number;
    project_id: number;
    task_title: string;
    task_desc?: string;
    priority: TaskStatus | number; // sometimes backend returns int
    status: TaskStatus | number;
    progress: number;

    // AI Enhanced Fields
    match_score?: number;
    relevance_analysis?: string;
    key_modules?: string[]; // strings or objects
    technical_challenges?: string[];
    implementation_complexity?: string;
    deliverables?: string[];

    created_at?: number;
    updated_at?: number;
    start_date?: number | string;
    end_date?: number | string;
}
