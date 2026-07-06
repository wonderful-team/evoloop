// 项目管理 Hook

import { useEffect, useCallback } from 'react';
import { ProjectManager } from '@/services/projects/ProjectManager';
import { useProjectStore } from '@/stores/projectStore';
import { useDeviceStore } from '@/stores/deviceStore';
import { useConversationStore } from '@/stores/conversationStore';
import { GLOBAL_PROJECT } from '@/types';

interface UseProjectsOptions {
  autoFetch?: boolean;
}

export function useProjects(options: UseProjectsOptions = {}) {
  const { autoFetch = true } = options;
  const store = useProjectStore();
  const deviceKey = useDeviceStore((state) => state.currentDevice?.deviceKey);
  const { projects, currentProject, isGlobalMode, isLoading, error } = store;

  // 自动获取项目列表
  useEffect(() => {
    if (autoFetch) {
      ProjectManager.fetchProjects(deviceKey).catch(console.error);
    }
  }, [autoFetch, deviceKey]);

  // 刷新项目列表
  const refresh = useCallback(async () => {
    return ProjectManager.fetchProjects(deviceKey);
  }, [deviceKey]);

  // 切换项目 —— 原子化更新 project + conversation store
  const switchProject = useCallback(async (projectId: number) => {
    const activeDeviceKey = useDeviceStore.getState().currentDevice?.deviceKey;
    await ProjectManager.switchProject(projectId, activeDeviceKey || '');
    useConversationStore.getState().switchProject(projectId);
  }, []);

  // 切换到全局模式（仅切换项目，不清除设备）
  const switchGlobal = useCallback(() => {
    useProjectStore.getState().setCurrentProject(GLOBAL_PROJECT);
    useConversationStore.getState().switchProject(0);
  }, []);

  return {
    projects,
    currentProject,
    isGlobalMode,
    isLoading,
    error,
    projectCount: (projects || []).length,
    refresh,
    switchProject,
    switchGlobal,
  };
}

// 单个项目 Hook
export function useProject(projectId: number | null) {
  const store = useProjectStore();
  const project = projectId
    ? (store.projects || []).find((p) => p.id === projectId)
    : null;

  const switchToThis = useCallback(async () => {
    if (!projectId) return null;
    const activeDeviceKey = useDeviceStore.getState().currentDevice?.deviceKey;
    return ProjectManager.switchProject(projectId, activeDeviceKey || '');
  }, [projectId]);

  return {
    project,
    isCurrent: store.currentProject?.id === projectId,
    switchToThis,
  };
}
