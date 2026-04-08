// 项目 API
// 混合架构：
// - 查询类 (列表、详情): Mobile → MC
// - 控制类 (切换项目): Mobile → Gateway → Desktop

import { api } from './client';
import { GATEWAY_API, MEMBER_API } from '@/constants/api';
import {
  ApiResponse,
  Project,
  ProjectSwitchRequest,
  ProjectSwitchResponse,
} from '@/types';

export const projectApi = {
  // 获取项目列表 (MC 存储)
  getProjects: async (): Promise<Project[]> => {
    const response = await api.get<ApiResponse<Project[]>>(
      MEMBER_API.PROJECTS
    );
    return response.data;
  },

  // 切换项目 (指令类 → Gateway → Desktop)
  switchProject: async (
    data: ProjectSwitchRequest
  ): Promise<ProjectSwitchResponse> => {
    const response = await api.post<ApiResponse<ProjectSwitchResponse>>(
      GATEWAY_API.COMMAND_EXECUTE,
      {
        device_id: data.deviceId,
        command_type: 'project_switch',
        content: { project_id: data.projectId },
      }
    );
    return response.data;
  },

  // 获取项目详情 (MC 存储)
  getProjectDetail: async (id: number): Promise<Project> => {
    const response = await api.get<ApiResponse<Project>>(
      MEMBER_API.PROJECT_DETAIL(id)
    );
    return response.data;
  },
};
