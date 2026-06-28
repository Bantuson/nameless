import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from './App';
import { ActiveProjectProvider } from './ActiveProjectContext';
import { ApiProvider } from './api/context';
import { MockNamelessApi } from './api/MockNamelessApi';
import { DEMO_PROJECT_ID } from './api/fixtures';

function renderApp() {
  const api = new MockNamelessApi();
  return render(
    <ApiProvider client={api}>
      <ActiveProjectProvider initialId={null}>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </ActiveProjectProvider>
    </ApiProvider>,
  );
}

describe('App shell', () => {
  it('defaults to Capture, auto-selects the seeded project, and shows its fragments', async () => {
    renderApp();
    expect(await screen.findByText(/Chorus hook hum/i)).toBeInTheDocument();
    // The active project defaulted to the seeded one (shown in the header selector).
    expect(screen.getByRole('combobox', { name: 'Project' })).toHaveValue(DEMO_PROJECT_ID);
    expect(screen.getByText('Late Night Tape')).toBeInTheDocument();
  });

  it('navigates between screens via the primary nav', async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByText(/Chorus hook hum/i);

    await user.click(screen.getByRole('link', { name: 'Reference' }));
    expect(await screen.findByText('amapiano')).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: 'Project' }));
    expect(await screen.findByRole('heading', { name: 'Project', level: 2 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Sample credits' })).toBeInTheDocument();
  });
});
