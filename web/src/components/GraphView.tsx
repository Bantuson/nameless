/**
 * Pure rendering of a project's fragment graph (UI-04).
 *
 * Each node is a card: kind, provenance, lifecycle state, intent note, and key/tempo once analyzed.
 * Lineage edges are shown inline ("derives from …") and summarized. Kept accessible as a labelled
 * list rather than an unlabelled SVG — for a thin M0 tool, legible nodes beat a force-directed canvas.
 */

import type { FragmentNode, ProjectGraph } from '../api/types';
import { kindLabel, notePreview, shortId } from '../lib/format';
import { ProvenanceTag, StatePill } from './badges';
import { EmptyState } from './ui';

export function GraphView({ graph }: { graph: ProjectGraph }): JSX.Element {
  if (graph.nodes.length === 0) {
    return <EmptyState>This project has no fragments yet.</EmptyState>;
  }

  const byId = new Map<string, FragmentNode>(graph.nodes.map((n) => [n.id, n]));

  return (
    <div className="graph">
      <p className="graph__summary">
        {graph.nodes.length} fragment{graph.nodes.length === 1 ? '' : 's'} · {graph.edges.length} lineage
        edge{graph.edges.length === 1 ? '' : 's'}
      </p>
      <ul className="graph__nodes" aria-label="Project fragment graph">
        {graph.nodes.map((n) => {
          const parent = n.parent_fragment_id ? byId.get(n.parent_fragment_id) : undefined;
          return (
            <li key={n.id} className="graph-node">
              <div className="graph-node__head">
                <span className="graph-node__kind">{kindLabel(n.kind)}</span>
                <ProvenanceTag provenance={n.provenance} />
                <StatePill state={n.state} />
                <code className="graph-node__id" title={n.id}>
                  {shortId(n.id)}
                </code>
              </div>
              <p className="graph-node__note">{notePreview(n.note, 140)}</p>
              <p className="graph-node__features">
                {n.key || n.tempo_bpm != null ? (
                  <>
                    <span className="graph-node__feat">key {n.key ?? '—'}</span>
                    <span className="graph-node__feat">
                      tempo {n.tempo_bpm != null ? `${Math.round(n.tempo_bpm)} BPM` : '—'}
                    </span>
                  </>
                ) : (
                  <span className="graph-node__feat graph-node__feat--muted">not analyzed yet</span>
                )}
              </p>
              {parent ? (
                <p className="graph-node__lineage">
                  ↳ derives from <code title={parent.id}>{shortId(parent.id)}</code> —{' '}
                  <span className="graph-node__lineage-note">{notePreview(parent.note, 60)}</span>
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
