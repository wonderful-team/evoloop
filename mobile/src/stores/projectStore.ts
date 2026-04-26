// 项目状态管理

import { create } from 'zustand';
import { Project, GLOBAL_PROJECT, isGlobalProject } from '@/types';

interface ProjectState {
  projects: Project[];
  currentProject: Project | null;
  isGlobalMode: boolean;
  isLoading: boolean;
  error: Error | null;

  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project | null) => void;
  setGlobalMode: (enabled: boolean) => void;
  addProject: (project: Project) => void;
  updateProject: (id: number, updates: Partial<Project>) => void;
  removeProject: (id: number) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: Error | null) => void;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  currentProject: null,
  isGlobalMode: false,
  isLoading: false,
  error: null,

  setProjects: (projects) => set({ projects }),

  setCurrentProject: (project) => set({
    currentProject: project,
    isGlobalMode: isGlobalProject(project),
  }),

  setGlobalMode: (enabled) => {
    if (enabled) {
      set({ currentProject: GLOBAL_PROJECT, isGlobalMode: true });
    } else {
      const { projects } = get();
      if (projects.length > 0) {
        set({ currentProject: projects[0], isGlobalMode: false });
      } else {
        set({ currentProject: null, isGlobalMode: false });
      }
    }
  },

  addProject: (project) => {
    const { projects } = get();
    set({ projects: [...projects, project] });
  },

  updateProject: (id, updates) => {
    const { projects } = get();
    set({
      projects: projects.map((p) =>
        p.id === id ? { ...p, ...updates } : p
      ),
    });
  },

  removeProject: (id) => {
    const { projects, currentProject } = get();
    set({
      projects: projects.filter((p) => p.id !== id),
      currentProject: currentProject?.id === id ? null : currentProject,
    });
  },

  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
}));
