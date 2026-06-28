/**
 * `HttpNamelessApi` — the REAL adapter. Talks to the Rust axum control plane over HTTP.
 *
 * This is the production implementation of the {@link NamelessApi} port. It is complete and real, but
 * **env-gated**: the axum server is built in `crates/` yet is not run on the 4GB dev box, so this
 * adapter is not exercised against a live server here. Point it at a running control plane by setting
 * `VITE_NAMELESS_CLIENT=http` and `VITE_API_BASE_URL` (see `.env.example`), then everything above —
 * unchanged — runs against real data.
 *
 * Audio never travels as JSON: `capture` and `uploadReference` send the file as multipart form-data;
 * every response is the compact summary the server's `output.rs` already emits.
 */

import type { NamelessApi } from './NamelessApi';
import { ApiError, IncompleteAttributionError, NotFoundError } from './errors';
import type { AttributionField } from './types';
import type {
  AddSampleInput,
  AttachReferenceInput,
  AttachReferenceResult,
  CaptureInput,
  CaptureResult,
  Credits,
  FragmentDetail,
  FragmentSummary,
  Project,
  ProjectGraph,
  ReferenceListItem,
  ReferenceUploadInput,
  ReferenceUploadResult,
  ReferenceView,
  SampleAddResult,
  SampleView,
  StemSummary,
  Uuid,
} from './types';

export interface HttpNamelessApiOptions {
  baseUrl: string;
  /** Injectable for tests; defaults to the global `fetch`. */
  fetchFn?: typeof fetch;
}

export class HttpNamelessApi implements NamelessApi {
  private readonly baseUrl: string;
  private readonly fetchFn: typeof fetch;

  constructor(opts: HttpNamelessApiOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, '');
    this.fetchFn = opts.fetchFn ?? globalThis.fetch.bind(globalThis);
  }

  // ---- projects ----

  listProjects(): Promise<Project[]> {
    return this.getJson('/projects');
  }

  createProject(title: string): Promise<Project> {
    return this.sendJson('POST', '/projects', { title });
  }

  // ---- capture (UI-01) ----

  capture(input: CaptureInput): Promise<CaptureResult> {
    const form = new FormData();
    form.append('file', input.file, input.fileName);
    form.append('note', input.note);
    form.append('kind', input.kind);
    return this.sendForm('POST', `/projects/${enc(input.projectId)}/fragments`, form);
  }

  listFragments(projectId?: Uuid): Promise<FragmentSummary[]> {
    const q = projectId ? `?project=${enc(projectId)}` : '';
    return this.getJson(`/fragments${q}`);
  }

  getFragment(id: Uuid): Promise<FragmentDetail> {
    return this.getJson(`/fragments/${enc(id)}`);
  }

  // ---- reference (UI-02) ----

  listReferences(): Promise<ReferenceListItem[]> {
    return this.getJson('/references');
  }

  uploadReference(input: ReferenceUploadInput): Promise<ReferenceUploadResult> {
    const form = new FormData();
    form.append('file', input.file, input.fileName);
    if (input.title) form.append('title', input.title);
    if (input.artist) form.append('artist', input.artist);
    return this.sendForm('POST', '/references', form);
  }

  getReferenceSummary(id: Uuid): Promise<ReferenceView> {
    return this.getJson(`/references/${enc(id)}`);
  }

  attachReference(input: AttachReferenceInput): Promise<AttachReferenceResult> {
    return this.sendJson('POST', `/projects/${enc(input.projectId)}/references`, {
      referenceId: input.referenceId,
      role: input.role,
    });
  }

  // ---- stem library + sampling (UI-03) ----

  separateStems(trackId: Uuid): Promise<{ reference: Uuid; enqueued_job: Uuid }> {
    return this.sendJson('POST', `/tracks/${enc(trackId)}/stems/separate`, {});
  }

  listStems(trackId: Uuid): Promise<StemSummary[]> {
    return this.getJson(`/tracks/${enc(trackId)}/stems`);
  }

  addSample(input: AddSampleInput): Promise<SampleAddResult> {
    return this.sendJson('POST', `/projects/${enc(input.projectId)}/samples`, {
      stemId: input.stemId,
      artist: input.artist,
      startMs: input.startMs,
      endMs: input.endMs,
      rights: input.rights,
      title: input.title,
    });
  }

  getSample(fragmentId: Uuid): Promise<SampleView> {
    return this.getJson(`/samples/${enc(fragmentId)}`);
  }

  // ---- project graph + credits (UI-04) ----

  getProjectGraph(projectId: Uuid): Promise<ProjectGraph> {
    return this.getJson(`/projects/${enc(projectId)}/graph`);
  }

  getCredits(projectId: Uuid): Promise<Credits> {
    return this.getJson(`/projects/${enc(projectId)}/credits`);
  }

  // ---- transport ----

  private async getJson<T>(path: string): Promise<T> {
    const res = await this.fetchFn(this.url(path), { headers: { Accept: 'application/json' } });
    return this.parse<T>(res, path);
  }

  private async sendJson<T>(method: string, path: string, body: unknown): Promise<T> {
    const res = await this.fetchFn(this.url(path), {
      method,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
    return this.parse<T>(res, path);
  }

  private async sendForm<T>(method: string, path: string, form: FormData): Promise<T> {
    // No Content-Type header — the browser sets the multipart boundary itself.
    const res = await this.fetchFn(this.url(path), { method, body: form, headers: { Accept: 'application/json' } });
    return this.parse<T>(res, path);
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  private async parse<T>(res: Response, path: string): Promise<T> {
    if (res.ok) {
      return (await res.json()) as T;
    }
    // Map the server's error contract to typed client errors.
    const body = await safeJson(res);
    if (res.status === 404) throw new NotFoundError(path);
    if (res.status === 422 && body && (body as { error?: string }).error === 'incomplete_attribution') {
      const missing = ((body as { missing?: AttributionField[] }).missing ?? []) as AttributionField[];
      throw new IncompleteAttributionError(missing);
    }
    let message = `request to ${path} failed (${res.status})`;
    if (body && typeof (body as { message?: unknown }).message === 'string') {
      message = (body as { message: string }).message;
    }
    throw new ApiError(message, res.status);
  }
}

function enc(id: string): string {
  return encodeURIComponent(id);
}

async function safeJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}
