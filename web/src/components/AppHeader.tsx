/**
 * The app shell header — brand, primary navigation, and the active-project control.
 *
 * Presentational: it receives the projects + handlers as props and owns only the tiny "new project"
 * input. Navigation uses router `NavLink`s (the shell is allowed to know about routing).
 */

import { useState, type FormEvent } from 'react';
import { NavLink } from 'react-router-dom';
import type { Project, Uuid } from '../api/types';
import { Button, Field } from './ui';

const NAV = [
  { to: '/capture', label: 'Capture' },
  { to: '/reference', label: 'Reference' },
  { to: '/library', label: 'Stem Library' },
  { to: '/project', label: 'Project' },
];

export function AppHeader({
  projects,
  activeProjectId,
  onSelectProject,
  onCreateProject,
  creatingProject,
}: {
  projects: Project[];
  activeProjectId: Uuid | null;
  onSelectProject: (id: Uuid) => void;
  onCreateProject: (title: string) => void;
  creatingProject: boolean;
}): JSX.Element {
  const [newTitle, setNewTitle] = useState('');

  function handleCreate(e: FormEvent): void {
    e.preventDefault();
    const title = newTitle.trim();
    if (title === '') return;
    onCreateProject(title);
    setNewTitle('');
  }

  return (
    <header className="app__header">
      <div className="app__brand">
        <span className="app__brand-mark" aria-hidden="true" />
        <span className="app__brand-name">Nameless</span>
        <span className="app__brand-tag">audio-native composition · M0</span>
      </div>

      <nav className="app__nav" aria-label="Primary">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `app__nav-link ${isActive ? 'app__nav-link--active' : ''}`.trim()}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="app__project">
        <Field label="Project">
          {({ id }) => (
            <select
              id={id}
              className="input input--inline"
              value={activeProjectId ?? ''}
              onChange={(e) => onSelectProject(e.target.value)}
              disabled={projects.length === 0}
            >
              {projects.length === 0 ? <option value="">No projects yet</option> : null}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          )}
        </Field>
        <form className="app__new-project" onSubmit={handleCreate} aria-label="Create a project">
          <Field label="New project">
            {({ id }) => (
              <input
                id={id}
                className="input input--inline"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Title…"
                autoComplete="off"
              />
            )}
          </Field>
          <Button type="submit" variant="ghost" busy={creatingProject} disabled={newTitle.trim() === ''}>
            Create
          </Button>
        </form>
      </div>
    </header>
  );
}
