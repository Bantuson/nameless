/** A project's fragment graph + credits (UI-04), over the injected client. */

import { useApi } from '../api/context';
import type { Credits, ProjectGraph, Uuid } from '../api/types';
import { useAsyncData } from './useAsyncData';

export interface UseProjectGraph {
  graph: ProjectGraph | undefined;
  loading: boolean;
  error: Error | undefined;
  refresh: () => void;
}

export function useProjectGraph(projectId: Uuid | null): UseProjectGraph {
  const api = useApi();
  const { data, loading, error, refresh } = useAsyncData(
    () => (projectId ? api.getProjectGraph(projectId) : Promise.resolve<ProjectGraph | undefined>(undefined)),
    [api, projectId],
  );
  return { graph: data, loading, error, refresh };
}

export interface UseCredits {
  credits: Credits | undefined;
  loading: boolean;
  error: Error | undefined;
  refresh: () => void;
}

export function useCredits(projectId: Uuid | null): UseCredits {
  const api = useApi();
  const { data, loading, error, refresh } = useAsyncData(
    () => (projectId ? api.getCredits(projectId) : Promise.resolve<Credits | undefined>(undefined)),
    [api, projectId],
  );
  return { credits: data, loading, error, refresh };
}
