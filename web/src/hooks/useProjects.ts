/** Projects list + create, over the injected client. */

import { useCallback } from 'react';
import { useApi } from '../api/context';
import type { Project } from '../api/types';
import { useAsyncData } from './useAsyncData';

export interface UseProjects {
  projects: Project[];
  loading: boolean;
  error: Error | undefined;
  refresh: () => void;
  createProject: (title: string) => Promise<Project>;
}

export function useProjects(): UseProjects {
  const api = useApi();
  const { data, loading, error, refresh } = useAsyncData(() => api.listProjects(), [api]);

  const createProject = useCallback(
    async (title: string) => {
      const project = await api.createProject(title);
      refresh();
      return project;
    },
    [api, refresh],
  );

  return { projects: data ?? [], loading, error, refresh, createProject };
}
