/** A project's fragments + the capture action (UI-01), over the injected client. */

import { useCallback } from 'react';
import { useApi } from '../api/context';
import type { CaptureResult, FragmentKind, FragmentSummary, Uuid } from '../api/types';
import { useAsyncData } from './useAsyncData';

/** What the capture form supplies; the project id is injected by the hook. */
export interface CaptureFormInput {
  note: string;
  kind: FragmentKind;
  file: Blob;
  fileName: string;
}

export interface UseFragments {
  fragments: FragmentSummary[];
  loading: boolean;
  error: Error | undefined;
  refresh: () => void;
  capture: (input: CaptureFormInput) => Promise<CaptureResult>;
}

export function useFragments(projectId: Uuid | null): UseFragments {
  const api = useApi();
  const { data, loading, error, refresh } = useAsyncData(
    () => (projectId ? api.listFragments(projectId) : Promise.resolve<FragmentSummary[]>([])),
    [api, projectId],
  );

  const capture = useCallback(
    async (input: CaptureFormInput) => {
      if (!projectId) throw new Error('no active project to capture into');
      const result = await api.capture({ projectId, ...input });
      refresh();
      return result;
    },
    [api, projectId, refresh],
  );

  return { fragments: data ?? [], loading, error, refresh, capture };
}
