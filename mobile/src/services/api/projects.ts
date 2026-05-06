// 项目 API
// 混合架构：
// - 查询类 (列表、详情): Mobile → MC
// - 控制类 (切换项目): Mobile → Gateway → Desktop

import { api } from './client';
import {
  ApiResponse,
  Project,
  ProjectSwitchRequest,
  ProjectSwitchResponse,
} from '@/types';

export interface ProjectFile {
  path: string;
  name: string;
  type: 'file' | 'directory';
  size?: number;
  modifiedTime?: string;
}

export const projectApi = {
  // 获取项目列表 (MC 存储)
  // 后端实际接口: GET /member/projectmanage/api/projectOpen/projects
  // 响应格式: { code: 0, data: { list: [...] }, message: 'success' }
  getProjects: async (): Promise<Project[]> => {
    const response = await api.get<ApiResponse<{ list: any[] }>>(
      `/member/projectmanage/api/projectOpen/projects`
    );
    const list = response.data?.list || [];
    return list.map((p: any) => ({
      id: p.project_id,
      name: p.project_name || '未命名项目',
      description: p.project_desc || '',
      rootPath: p.external_path || '',
      isActive: false,
    }));
  },

  // 切换项目 (指令类 → Gateway → Desktop)
  switchProject: async (
    data: ProjectSwitchRequest
  ): Promise<ProjectSwitchResponse> => {
    const response = await api.post<ApiResponse<ProjectSwitchResponse>>(
      `/gateway/api/v1/command/send`,
      {
        device_key: data.deviceKey,
        command_type: 'project_switch',
        payload: { project_id: data.projectId },
      }
    );
    return response.data;
  },

  // 获取项目详情 (MC 存储)
  getProjectDetail: async (id: number): Promise<Project> => {
    const response = await api.get<ApiResponse<Project>>(
      `/member/projectmanage/api/projects/${id}`
    );
    return response.data;
  },

  // 获取项目文件列表
  getProjectFiles: async (projectId: number, path: string = ''): Promise<ProjectFile[]> => {
    const response = await api.get<ApiResponse<ProjectFile[]>>(
      `/member/projectmanage/api/projects/${projectId}/files`,
      { params: { path } }
    );
    return response.data || [];
  },
};
