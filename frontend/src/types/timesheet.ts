
export interface TimesheetEntry {
    id: number;
    project_id: number;
    member_id: number;
    member_name?: string;
    work_date: string; // YYYY-MM-DD
    hours: number;
    description: string;
    work_type: string;
    created_at?: string;
}

export interface TimesheetQuickAdd {
    project_id: number;
    hours: number;
    description: string;
    work_type?: string;
}
