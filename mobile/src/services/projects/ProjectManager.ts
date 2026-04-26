// 项目管理服务

import { projectApi } from '@/services/api/projects';
import { Project, GLOBAL_PROJECT, isGlobalProject } from '@/types';
import { useProjectStore } from '@/stores/projectStore';
import { useDeviceStore } from '@/stores/deviceStore';

export class ProjectManager {
  // 获取项目列表
  static async fetchProjects(): Promise<Project[]> {
    const store = useProjectStore.getState();
    store.setLoading(true);
    store.setError(null);

    try {
      const projects = await projectApi.getProjects();
      store.setProjects(projects || []);
      
      // 设置当前项目（如果没有设置的话，默认进入全局模式）
      const currentProject = store.currentProject;
      if (!currentProject) {
        store.setCurrentProject(GLOBAL_PROJECT);
      }
      
      return projects;
    } catch (error) {
      const err = error instanceof Error ? error : new Error('获取项目列表失败');
      store.setError(err);
      throw err;
    } finally {
      store.setLoading(false);
    }
  }

  // 切换项目（支持全局模式）
  // 项目归属于设备，指令只发送给当前选中的设备
  static async switchProject(projectId: number): Promise<Project> {
    const store = useProjectStore.getState();
    const deviceStore = useDeviceStore.getState();
    const currentDevice = deviceStore.currentDevice;
    store.setLoading(true);

    try {
      // 全局模式：直接更新 store，不调用 Gateway
      if (projectId === 0 || isGlobalProject({ id: projectId } as Project)) {
        const projects = (store.projects || []).map(p => ({
          ...p,
          isActive: false,
        }));
        store.setProjects(projects);
        store.setCurrentProject(GLOBAL_PROJECT);
        return GLOBAL_PROJECT;
      }

      // 非全局模式：向当前设备发送 project_switch 指令
      await projectApi.switchProject({
        deviceKey: currentDevice?.deviceKey || '',
        projectId,
      });

      // 从列表中找到目标项目
      const targetProject = (store.projects || []).find(p => p.id === projectId);
      if (!targetProject) {
        throw new Error('项目不存在');
      }

      // 更新本地项目状态
      const projects = (store.projects || []).map(p => ({
        ...p,
        isActive: p.id === projectId,
      }));
      store.setProjects(projects);
      store.setCurrentProject(targetProject);

      return targetProject;
    } finally {
      store.setLoading(false);
    }
  }

  // 获取当前项目
  static getCurrentProject(): Project | null {
    return useProjectStore.getState().currentProject;
  }

  // 设置当前项目
  static setCurrentProject(project: Project | null): void {
    const store = useProjectStore.getState();
    store.setCurrentProject(project);
  }
}
