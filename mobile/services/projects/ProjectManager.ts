// 项目管理服务

import { projectApi } from '@/services/api/projects';
import { Project } from '@/types';
import { useProjectStore } from '@/stores/projectStore';

export class ProjectManager {
  // 获取项目列表
  static async fetchProjects(): Promise<Project[]> {
    const store = useProjectStore.getState();
    store.setLoading(true);
    store.setError(null);

    try {
      const projects = await projectApi.getProjects();
      store.setProjects(projects);
      
      // 设置当前项目（如果没有设置的话）
      const currentProject = store.currentProject;
      if (!currentProject && projects.length > 0) {
        const activeProject = projects.find(p => p.isActive);
        if (activeProject) {
          store.setCurrentProject(activeProject);
        }
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

  // 切换项目
  static async switchProject(projectId: number): Promise<Project> {
    const store = useProjectStore.getState();
    store.setLoading(true);

    try {
      const result = await projectApi.switchProject({ project_id: projectId });
      
      // 更新本地项目状态
      const projects = store.projects.map(p => ({
        ...p,
        isActive: p.id === projectId,
      }));
      store.setProjects(projects);
      store.setCurrentProject(result.project);
      
      return result.project;
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
