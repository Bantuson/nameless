import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CaptureScreen } from './CaptureScreen';
import { renderWithApi } from '../test/renderWithApi';

describe('CaptureScreen (UI-01)', () => {
  it('renders the seeded fragments for the active project', async () => {
    renderWithApi(<CaptureScreen />);
    expect(await screen.findByText(/Chorus hook hum/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Capture' })).toBeInTheDocument();
  });

  it('captures a fragment + note and lists it by id/state', async () => {
    const user = userEvent.setup();
    renderWithApi(<CaptureScreen />);
    await screen.findByText(/Chorus hook hum/i);

    const file = new File(['fake-audio-bytes'], 'idea.wav', { type: 'audio/wav' });
    await user.upload(screen.getByLabelText('Audio file'), file);
    await user.type(screen.getByLabelText('Intent note'), 'late-night vocal run idea');
    await user.click(screen.getByRole('button', { name: /capture fragment/i }));

    expect(await screen.findByText(/Captured fragment/i)).toBeInTheDocument();
    expect(await screen.findByText(/late-night vocal run idea/i)).toBeInTheDocument();
  });

  it('shows the no-project notice when no project is active', () => {
    renderWithApi(<CaptureScreen />, { activeProjectId: null });
    expect(screen.getByText(/No project selected/i)).toBeInTheDocument();
  });
});
