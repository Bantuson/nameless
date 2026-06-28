import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StemLibraryScreen } from './StemLibraryScreen';
import { renderWithApi } from '../test/renderWithApi';

describe('StemLibraryScreen (UI-03)', () => {
  it('lists a track\'s retained stems', async () => {
    renderWithApi(<StemLibraryScreen />);
    expect(await screen.findByText('Piano')).toBeInTheDocument();
    expect(screen.getByText('Vocals')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Stem Library' })).toBeInTheDocument();
  });

  it('surfaces the attribution form with the gate and "attribution is not permission", then adds a sample', async () => {
    const user = userEvent.setup();
    renderWithApi(<StemLibraryScreen />);
    await screen.findByText('Piano');

    // Promote the first stem.
    const useButtons = await screen.findAllByRole('button', { name: /use as sample/i });
    await user.click(useButtons[0]);

    // The form appears, the submit is gated, and the honesty notice is shown.
    const submit = await screen.findByRole('button', { name: /add as sample/i });
    expect(submit).toBeDisabled();
    expect(screen.getByText(/Attribution is not permission/i)).toBeInTheDocument();
    expect(screen.getByText(/Still required/i)).toBeInTheDocument();

    // Complete the attribution (title falls back to the track title).
    await user.type(screen.getByLabelText('Source artist'), 'Esther Vale');
    await user.type(screen.getByLabelText('Start (ms)'), '1000');
    await user.type(screen.getByLabelText('End (ms)'), '5000');
    await user.selectOptions(screen.getByLabelText('Rights status'), 'royalty_free');

    expect(submit).toBeEnabled();
    await user.click(submit);

    expect(await screen.findByText(/Sample added/i)).toBeInTheDocument();
  });

  it('shows the no-project notice when no project is active', () => {
    renderWithApi(<StemLibraryScreen />, { activeProjectId: null });
    expect(screen.getByText(/No project selected/i)).toBeInTheDocument();
  });
});
