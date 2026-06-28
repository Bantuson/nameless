/**
 * Pure derivation of a project's lineage edges from its fragment nodes.
 *
 * An edge exists wherever a node names a `parent_fragment_id` that is also present in the node set.
 * Kept pure (nodes in, edges out) so the graph shape is unit-testable without a backend, and reused
 * by the `MockNamelessApi` to build `ProjectGraph.edges`.
 */

import type { FragmentNode, GraphEdge } from '../api/types';

export function deriveEdges(nodes: readonly FragmentNode[]): GraphEdge[] {
  const ids = new Set(nodes.map((n) => n.id));
  const edges: GraphEdge[] = [];
  for (const n of nodes) {
    if (n.parent_fragment_id && ids.has(n.parent_fragment_id)) {
      edges.push({ from: n.parent_fragment_id, to: n.id });
    }
  }
  return edges;
}

/** Root nodes: those with no in-graph parent (the capture/sample origins of a lineage). */
export function rootNodes(nodes: readonly FragmentNode[]): FragmentNode[] {
  const ids = new Set(nodes.map((n) => n.id));
  return nodes.filter((n) => !n.parent_fragment_id || !ids.has(n.parent_fragment_id));
}
