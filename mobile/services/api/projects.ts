// 项目 API

import { api } from './client';
import { GATEWAY_API } from '@/constants/api';
import {
  ApiResponse,
  Project,
  ProjectSwitchRequest,
  ProjectSwitchResponse,
} from '@/types';

export const projectApi = {
  // 获取项目列表
  getProjects: async (): Promise<Project[]> => {
    const response = await api.get<ApiResponse<Project[]>>(
      GATEWAY_API.PROJECTS
    );
    return response.data;
  },

  // 切换项目
  switchProject: async (
    data: ProjectSwitchRequest
  ): Promise<ProjectSwitchResponse> => {
    const response = await api.post<ApiResponse<ProjectSwitchResponse>>(
      GATEWAY_API.PROJECT_SWITCH,
      data
    );
    return response.data;
  },

  // 获取项目详情
  getProjectDetail: async (id: number): Promise<Project> => {
    const response = await api.get<ApiResponse<Project>>(
      GATEWAY_API.PROJECT_DETAIL(id)
    );
    return response.data;
  },
};
