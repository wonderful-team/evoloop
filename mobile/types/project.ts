// 项目相关类型

export interface Project {
  id: number;
  name: string;
  description?: string;
  rootPath: string;
  isActive: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface ProjectSwitchRequest {
  project_id: number;
}

export interface ProjectSwitchResponse {
  project: Project;
  message?: string;
}
