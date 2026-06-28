/**
 * Project screen (UI-04) — the project's fragment graph (nodes + notes + key/tempo) and its sample
 * credits list. Read-only composition of `useProjectGraph` + `useCredits` with the pure views.
 */

import { useActiveProject } from '../ActiveProjectContext';
import { CreditsList } from '../components/CreditsList';
import { GraphView } from '../components/GraphView';
import { Button, ErrorMessage, Loading } from '../components/ui';
import { useCredits, useProjectGraph } from '../hooks/useProject';
import { NoProjectNotice } from './common';

export function ProjectScreen(): JSX.Element {
  const { activeProjectId } = useActiveProject();
  const graph = useProjectGraph(activeProjectId);
  const credits = useCredits(activeProjectId);

  if (!activeProjectId) return <NoProjectNotice action="view" />;

  function refreshAll(): void {
    graph.refresh();
    credits.refresh();
  }

  return (
    <section className="screen" aria-labelledby="project-title">
      <header className="screen__head">
        <div className="screen__head-row">
          <h2 id="project-title">Project</h2>
          <Button variant="ghost" onClick={refreshAll}>
            Refresh
          </Button>
        </div>
        <p className="screen__lead">
          The fragment graph is this project's memory — every captured, derived, and sampled fragment,
          with its intent note and key/tempo once analyzed. Below it, the sample credits.
        </p>
      </header>

      <section className="screen__section" aria-label="Fragment graph">
        <h3 className="screen__subtitle">Fragment graph</h3>
        {graph.loading ? <Loading label="Loading graph…" /> : null}
        {graph.error ? <ErrorMessage error={graph.error} /> : null}
        {graph.graph ? <GraphView graph={graph.graph} /> : null}
      </section>

      <section className="screen__section" aria-label="Sample credits">
        <h3 className="screen__subtitle">Sample credits</h3>
        {credits.loading ? <Loading label="Loading credits…" /> : null}
        {credits.error ? <ErrorMessage error={credits.error} /> : null}
        {credits.credits ? <CreditsList credits={credits.credits} /> : null}
      </section>
    </section>
  );
}
