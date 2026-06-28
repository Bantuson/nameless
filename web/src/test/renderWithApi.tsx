/**
 * Test helper — render a component tree with the {@link NamelessApi} injected (a `MockNamelessApi`
 * by default) plus the active-project + router providers. This is how every component/screen test
 * runs the real UI control flow against the fake client, with no backend.
 */

import { render, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { ActiveProjectProvider } from '../ActiveProjectContext';
import { ApiProvider } from '../api/context';
import { MockNamelessApi } from '../api/MockNamelessApi';
import type { NamelessApi } from '../api/NamelessApi';
import { DEMO_PROJECT_ID } from '../api/fixtures';

export interface RenderWithApiOptions {
  api?: NamelessApi;
  activeProjectId?: string | null;
  route?: string;
}

export function renderWithApi(
  ui: ReactElement,
  opts: RenderWithApiOptions = {},
): RenderResult & { api: NamelessApi } {
  const api = opts.api ?? new MockNamelessApi();
  const activeProjectId = opts.activeProjectId === undefined ? DEMO_PROJECT_ID : opts.activeProjectId;
  const result = render(
    <ApiProvider client={api}>
      <ActiveProjectProvider initialId={activeProjectId}>
        <MemoryRouter initialEntries={[opts.route ?? '/']}>{ui}</MemoryRouter>
      </ActiveProjectProvider>
    </ApiProvider>,
  );
  return { api, ...result };
}
