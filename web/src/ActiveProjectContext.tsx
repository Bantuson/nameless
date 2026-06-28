/**
 * The active-project selection — a tiny piece of cross-screen UI state.
 *
 * Capture and Project screens operate on "the project I'm working in". Rather than thread that id
 * through every route, we expose it via a small context with a setter. It carries no data-fetching
 * concern (that lives in the hooks) — just the chosen id.
 */

import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import type { Uuid } from './api/types';

interface ActiveProjectValue {
  activeProjectId: Uuid | null;
  setActiveProjectId: (id: Uuid | null) => void;
}

const ActiveProjectContext = createContext<ActiveProjectValue | null>(null);

export function ActiveProjectProvider({
  initialId = null,
  children,
}: {
  initialId?: Uuid | null;
  children: ReactNode;
}): JSX.Element {
  const [activeProjectId, setActiveProjectId] = useState<Uuid | null>(initialId);
  const value = useMemo(() => ({ activeProjectId, setActiveProjectId }), [activeProjectId]);
  return <ActiveProjectContext.Provider value={value}>{children}</ActiveProjectContext.Provider>;
}

export function useActiveProject(): ActiveProjectValue {
  const v = useContext(ActiveProjectContext);
  if (!v) throw new Error('useActiveProject must be used within an <ActiveProjectProvider>');
  return v;
}
