/**
 * The application shell + routes. Orchestration only: it loads projects, manages the active-project
 * default, and renders the four screens. It depends on the injected client (via the hooks), never on
 * a concrete adapter — so the very same tree runs against the mock in tests and the real server in prod.
 */

import { useEffect, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useActiveProject } from './ActiveProjectContext';
import { AppHeader } from './components/AppHeader';
import { useProjects } from './hooks/useProjects';
import { CaptureScreen } from './screens/CaptureScreen';
import { ProjectScreen } from './screens/ProjectScreen';
import { ReferenceScreen } from './screens/ReferenceScreen';
import { StemLibraryScreen } from './screens/StemLibraryScreen';

export function App(): JSX.Element {
  const { projects, createProject } = useProjects();
  const { activeProjectId, setActiveProjectId } = useActiveProject();
  const [creating, setCreating] = useState(false);

  // Default the active project to the first one once projects load.
  useEffect(() => {
    if (!activeProjectId && projects.length > 0) setActiveProjectId(projects[0].id);
  }, [projects, activeProjectId, setActiveProjectId]);

  async function handleCreate(title: string): Promise<void> {
    setCreating(true);
    try {
      const project = await createProject(title);
      setActiveProjectId(project.id);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <AppHeader
        projects={projects}
        activeProjectId={activeProjectId}
        onSelectProject={setActiveProjectId}
        onCreateProject={handleCreate}
        creatingProject={creating}
      />
      <main className="app__main" id="main">
        <Routes>
          <Route path="/" element={<Navigate to="/capture" replace />} />
          <Route path="/capture" element={<CaptureScreen />} />
          <Route path="/reference" element={<ReferenceScreen />} />
          <Route path="/library" element={<StemLibraryScreen />} />
          <Route path="/project" element={<ProjectScreen />} />
          <Route path="*" element={<Navigate to="/capture" replace />} />
        </Routes>
      </main>
      <footer className="app__footer">
        <p>
          Local-first · compact contract (ids + summaries, never raw audio) · the real control plane is
          env-gated. Personal/portfolio scope — attribution is not permission.
        </p>
      </footer>
    </div>
  );
}
