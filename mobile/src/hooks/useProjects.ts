// 项目管理 Hook

import { useEffect, useCallback } from 'react';
import { ProjectManager } from '@/services/projects/ProjectManager';
import { useProjectStore } from '@/stores/projectStore';
import { Project } from '@/types';

interface UseProjectsOptions {
  autoFetch?: boolean;
}

export function useProjects(options: UseProjectsOptions = {}) {
  const { autoFetch = true } = options;
  const store = useProjectStore();
  const { projects, currentProject, isLoading, error } = store;

  // 自动获取项目列表
  useEffect(() => {
    if (autoFetch) {
      ProjectManager.fetchProjects().catch(console.error);
    }
  }, [autoFetch]);

  // 刷新项目列表
  const refresh = useCallback(async () => {
    return ProjectManager.fetchProjects();
  }, []);

  // 切换项目
  const switchProject = useCallback(async (projectId: number) => {
    return ProjectManager.switchProject(projectId);
  }, []);

  // 设置当前项目
  const setCurrentProject = useCallback((project: Project | null) => {
    ProjectManager.setCurrentProject(project);
  }, []);

  return {
    projects,
    currentProject,
    isLoading,
    error,
    projectCount: projects.length,
    refresh,
    switchProject,
    setCurrentProject,
  };
}

// 单个项目 Hook
export function useProject(projectId: number | null) {
  const store = useProjectStore();
  const project = projectId
    ? store.projects.find((p) => p.id === projectId)
    : null;

  const switchToThis = useCallback(async () => {
    if (!projectId) return null;
    return ProjectManager.switchProject(projectId);
  }, [projectId]);

  return {
    project,
    isCurrent: store.currentProject?.id === projectId,
    switchToThis,
  };
}
