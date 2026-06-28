/** A track's stem library + separate + add-as-sample (UI-03), over the injected client. */

import { useCallback } from 'react';
import { useApi } from '../api/context';
import type { AddSampleInput, SampleAddResult, StemSummary, Uuid } from '../api/types';
import { useAsyncData } from './useAsyncData';

/** What the attribution form supplies; stem + project ids are injected by the caller. */
export interface AddSampleFormInput {
  stemId: Uuid;
  artist: string;
  startMs: number;
  endMs: number;
  rights: AddSampleInput['rights'];
  title?: string;
}

export interface UseStemLibrary {
  stems: StemSummary[];
  loading: boolean;
  error: Error | undefined;
  refresh: () => void;
  separate: () => Promise<void>;
  addSample: (projectId: Uuid, input: AddSampleFormInput) => Promise<SampleAddResult>;
}

export function useStemLibrary(trackId: Uuid | null): UseStemLibrary {
  const api = useApi();
  const { data, loading, error, refresh } = useAsyncData(
    () => (trackId ? api.listStems(trackId) : Promise.resolve<StemSummary[]>([])),
    [api, trackId],
  );

  const separate = useCallback(async () => {
    if (!trackId) throw new Error('no track selected to separate');
    await api.separateStems(trackId);
    refresh();
  }, [api, trackId, refresh]);

  const addSample = useCallback(
    (projectId: Uuid, input: AddSampleFormInput) => api.addSample({ projectId, ...input }),
    [api],
  );

  return { stems: data ?? [], loading, error, refresh, separate, addSample };
}
