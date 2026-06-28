import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { ProjectScreen } from './ProjectScreen';
import { renderWithApi } from '../test/renderWithApi';

describe('ProjectScreen (UI-04)', () => {
  it('renders the fragment graph with notes + key/tempo and lineage', async () => {
    renderWithApi(<ProjectScreen />);
    const graph = await screen.findByRole('list', { name: 'Project fragment graph' });

    // A node's intent note (scoped to the node-note element, not the lineage echo).
    expect(
      within(graph).getByText(/Chorus hook hum/i, { selector: '.graph-node__note' }),
    ).toBeInTheDocument();
    // Analyzed nodes carry key + tempo (the hum and its derived child both show C:min @ 112).
    expect(within(graph).getAllByText(/key C:min/i).length).toBeGreaterThanOrEqual(1);
    expect(within(graph).getAllByText(/112 BPM/i).length).toBeGreaterThanOrEqual(1);
    // The derived fragment shows its lineage edge.
    expect(within(graph).getByText(/derives from/i)).toBeInTheDocument();
  });

  it('renders the sample credits with the permission notice', async () => {
    renderWithApi(<ProjectScreen />);
    const creditsList = await screen.findByRole('list', { name: 'Sample credits' });
    expect(within(creditsList).getByText('Midnight Reverie')).toBeInTheDocument();
    expect(within(creditsList).getByText(/Esther Vale/i)).toBeInTheDocument();
    // The non-negotiable honesty line is present (banner + the rendered markdown sheet).
    expect(screen.getAllByText(/Attribution is not permission/i).length).toBeGreaterThan(0);
  });
});
