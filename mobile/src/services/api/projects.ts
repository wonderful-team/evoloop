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
import i18n from '@/locales';

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
  getProjects: async (deviceKey?: string): Promise<Project[]> => {
    const response = await api.get<ApiResponse<{ list: any[] }>>(
      `/member/projectmanage/api/projectOpen/projects`,
      {
        params: deviceKey ? { external_source: deviceKey } : {},
      }
    );
    const list = response.data?.list || [];
    return list.map((p: any) => ({
      id: p.project_id,
      name: p.project_name || i18n.t('projects.unnamedProject'),
      description: p.project_desc || '',
      rootPath: p.external_path || '',
      isActive: false,
    }));
  },

  // 切换项目
  switchProject: async (
    data: ProjectSwitchRequest
  ): Promise<ProjectSwitchResponse> => {
    const envelope = {
      version: '2.0',
      type: 'command.relay',
      timestamp: Math.floor(Date.now() / 1000),
      source: { kind: 'mobile' },
      target: { kind: 'agent', device_key: data.deviceKey },
      body: {
        action: 'project_switch',
        project_id: data.projectId,
        content: { project_id: data.projectId },
      },
    };
    const response = await api.post<ApiResponse<ProjectSwitchResponse>>(
      `/gateway/api/v1/message/send`,
      { target_device_key: data.deviceKey, envelope },
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
