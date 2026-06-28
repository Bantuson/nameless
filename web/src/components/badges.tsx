/** Pure badge components for fragment state, provenance, and rights status. */

import type { FragmentState, Provenance, RightsStatus } from '../api/types';
import { provenanceLabel, stateLabel } from '../lib/format';
import { rightsIsCautionary, rightsLabel } from '../lib/rights';

/** Group a state into a coarse phase, for color. */
function statePhase(state: FragmentState): 'early' | 'mid' | 'done' | 'reject' {
  switch (state) {
    case 'captured':
    case 'requested':
    case 'analyzing':
    case 'generating':
      return 'early';
    case 'analyzed':
    case 'generated':
    case 'evaluating':
    case 'promoted':
    case 'placed':
      return 'mid';
    case 'mixed':
    case 'rendered':
      return 'done';
    case 'rejected':
      return 'reject';
  }
}

export function StatePill({ state }: { state: FragmentState }): JSX.Element {
  return (
    <span className={`pill pill--state pill--${statePhase(state)}`} data-state={state}>
      {stateLabel(state)}
    </span>
  );
}

export function ProvenanceTag({ provenance }: { provenance: Provenance }): JSX.Element {
  return (
    <span className={`pill pill--prov pill--prov-${provenance}`} data-provenance={provenance}>
      {provenanceLabel(provenance)}
    </span>
  );
}

export function RightsTag({ rights }: { rights: RightsStatus }): JSX.Element {
  const caution = rightsIsCautionary(rights);
  return (
    <span className={`pill pill--rights ${caution ? 'pill--warn' : 'pill--ok'}`} data-rights={rights}>
      {rightsLabel(rights)}
    </span>
  );
}
