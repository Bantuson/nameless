/** Reference list + upload + attach (UI-02), and a single-reference summary loader. */

import { useCallback } from 'react';
import { useApi } from '../api/context';
import type {
  AttachReferenceResult,
  ReferenceListItem,
  ReferenceRole,
  ReferenceUploadResult,
  ReferenceView,
  Uuid,
} from '../api/types';
import { useAsyncData } from './useAsyncData';

export interface ReferenceUploadFormInput {
  file: Blob;
  fileName: string;
  title?: string;
  artist?: string;
}

export interface UseReferences {
  references: ReferenceListItem[];
  loading: boolean;
  error: Error | undefined;
  refresh: () => void;
  uploadReference: (input: ReferenceUploadFormInput) => Promise<ReferenceUploadResult>;
  attachReference: (referenceId: Uuid, projectId: Uuid, role: ReferenceRole) => Promise<AttachReferenceResult>;
}

export function useReferences(): UseReferences {
  const api = useApi();
  const { data, loading, error, refresh } = useAsyncData(() => api.listReferences(), [api]);

  const uploadReference = useCallback(
    async (input: ReferenceUploadFormInput) => {
      const result = await api.uploadReference(input);
      refresh();
      return result;
    },
    [api, refresh],
  );

  const attachReference = useCallback(
    (referenceId: Uuid, projectId: Uuid, role: ReferenceRole) =>
      api.attachReference({ referenceId, projectId, role }),
    [api],
  );

  return { references: data ?? [], loading, error, refresh, uploadReference, attachReference };
}

export interface UseReferenceSummary {
  reference: ReferenceView | undefined;
  loading: boolean;
  error: Error | undefined;
  refresh: () => void;
}

/** Load one reference's compact vibe/target summary. `null` id → nothing loaded. */
export function useReferenceSummary(referenceId: Uuid | null): UseReferenceSummary {
  const api = useApi();
  const { data, loading, error, refresh } = useAsyncData(
    () => (referenceId ? api.getReferenceSummary(referenceId) : Promise.resolve<ReferenceView | undefined>(undefined)),
    [api, referenceId],
  );
  return { reference: data, loading, error, refresh };
}
