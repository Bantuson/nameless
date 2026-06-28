/**
 * Composition root — wires the injected client, the providers, and the router, then mounts the app.
 * This is the only file that constructs concrete adapters (via `createClient`).
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { ActiveProjectProvider } from './ActiveProjectContext';
import { ApiProvider } from './api/context';
import { createClient } from './api/createClient';
import './styles.css';

const client = createClient();
const root = document.getElementById('root');
if (!root) throw new Error('#root not found');

createRoot(root).render(
  <StrictMode>
    <ApiProvider client={client}>
      <ActiveProjectProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ActiveProjectProvider>
    </ApiProvider>
  </StrictMode>,
);
