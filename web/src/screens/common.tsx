/** Shared screen-level scaffolding. */

import { Banner } from '../components/ui';

/** Shown when a screen needs an active project but none is selected. */
export function NoProjectNotice({ action }: { action: string }): JSX.Element {
  return (
    <section className="screen" aria-label="No project selected">
      <Banner tone="info" title="No project selected">
        Choose a project in the header, or create one, to {action} it.
      </Banner>
    </section>
  );
}
