/**
 * Typed API errors — the client surfaces failures as discriminable error classes, not bare strings,
 * so the UI can react precisely (mirroring the Rust `CliError` variants).
 */

import type { AttributionField } from './types';

/** A generic transport/server error (non-2xx with no more specific meaning). */
export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** A requested entity does not exist (mirrors `CliError::NotFound`). */
export class NotFoundError extends ApiError {
  constructor(what: string) {
    super(`not found: ${what}`, 404);
    this.name = 'NotFoundError';
  }
}

/**
 * The sample-attribution completeness gate rejected the request (mirrors
 * `CliError::IncompleteAttribution`). `missing` names exactly which fields must still be supplied —
 * the same typed field list the Rust `IncompleteAttribution` carries — so the form can highlight
 * them. No fragment, attribution, or job is created when this is thrown.
 */
export class IncompleteAttributionError extends ApiError {
  readonly missing: AttributionField[];

  constructor(missing: AttributionField[]) {
    super(`incomplete attribution: missing ${missing.join(', ')}`, 422);
    this.name = 'IncompleteAttributionError';
    this.missing = missing;
  }
}
