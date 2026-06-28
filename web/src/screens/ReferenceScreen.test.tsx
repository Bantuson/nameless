import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReferenceScreen } from './ReferenceScreen';
import { renderWithApi } from '../test/renderWithApi';

describe('ReferenceScreen (UI-02)', () => {
  it('shows the vibe + non-melodic sonic-target summary and the "context, never cloned" boundary', async () => {
    renderWithApi(<ReferenceScreen />);
    // Vibe + targets are surfaced.
    expect(await screen.findByText('amapiano')).toBeInTheDocument();
    expect(screen.getByText('110–114 BPM')).toBeInTheDocument();
    expect(screen.getByText('-9.4 LUFS')).toBeInTheDocument();
    // The embedding dimension is shown, never the vector.
    expect(screen.getByText(/512-d \(vector withheld\)/i)).toBeInTheDocument();
    // The honest non-cloning boundary is present.
    expect(screen.getByText(/Context, never cloned/i)).toBeInTheDocument();
  });

  it('attaches the reference to the active project', async () => {
    const user = userEvent.setup();
    renderWithApi(<ReferenceScreen />);
    await screen.findByText('amapiano');

    await user.click(screen.getByRole('button', { name: /attach to project/i }));
    expect(await screen.findByText(/Attached as/i)).toBeInTheDocument();
  });
});
