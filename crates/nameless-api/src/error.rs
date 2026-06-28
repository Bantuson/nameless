//! The HTTP error contract — a pure mapping from the control-plane [`CliError`] to a status + body.
//!
//! The web client (`web/src/api/HttpNamelessApi.ts` → `parse()`) discriminates on exactly two shapes:
//!
//! * **`404`** → `NotFoundError` (the body is ignored for 404s; we still send a `message`).
//! * **`422` with body `{"error":"incomplete_attribution","missing":[…]}`** → `IncompleteAttributionError`,
//!   where `missing` is the typed [`AttributionField`] list. EVERYTHING ELSE → a generic `ApiError`
//!   built from `{"message":"…"}` and the status code.
//!
//! So this module owns two things: the [`ApiError`] response type (its `IntoResponse` renders one of
//! the two bodies) and the [`From<CliError>`] mapping. Both are deliberately pure and free of I/O, so
//! they unit-test directly (see the crate tests) without spinning up the server.

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Serialize;

use nameless_cli::error::CliError;
use nameless_core::attribution::AttributionField;
use nameless_core::job::JobError;

/// A typed HTTP error: a status code plus one of the two body shapes the web client parses.
#[derive(Debug)]
pub struct ApiError {
    pub status: StatusCode,
    pub body: ApiErrorBody,
}

/// The two error body shapes (mirrors the client's `parse()` branches).
#[derive(Debug)]
pub enum ApiErrorBody {
    /// `{ "message": "…" }` — the generic shape for any non-attribution failure.
    Message(String),
    /// `{ "error": "incomplete_attribution", "missing": ["source_artist", …] }` — the sample gate.
    IncompleteAttribution { missing: Vec<&'static str> },
}

impl ApiError {
    pub fn new(status: StatusCode, msg: impl Into<String>) -> Self {
        Self {
            status,
            body: ApiErrorBody::Message(msg.into()),
        }
    }

    pub fn not_found(msg: impl Into<String>) -> Self {
        Self::new(StatusCode::NOT_FOUND, msg)
    }

    pub fn bad_request(msg: impl Into<String>) -> Self {
        Self::new(StatusCode::BAD_REQUEST, msg)
    }

    pub fn internal(msg: impl Into<String>) -> Self {
        Self::new(StatusCode::INTERNAL_SERVER_ERROR, msg)
    }
}

/// Map a typed [`AttributionField`] to the EXACT string the web `AttributionField` union uses.
///
/// IMPORTANT — this is a third, dedicated spelling, NOT a reuse of either built-in form:
/// * `AttributionField::as_str()` is CLI-flag-facing and returns `"artist"` / `"rights"`;
/// * the serde `rename_all = "snake_case"` derive would emit `"source_artist"` / `"rights_status"`.
///
/// The committed TS contract (`web/src/api/types.ts`) uses `"source_artist"` AND `"rights"`, so
/// neither form matches on its own — the wire mapping has to be authored. Keep this in lockstep with
/// the TS union; the crate test `attribution_field_wire_matches_ts_union` pins all seven values.
pub fn attribution_field_wire(f: AttributionField) -> &'static str {
    match f {
        AttributionField::SourceTrack => "source_track",
        AttributionField::Stem => "stem",
        AttributionField::SourceTitle => "source_title",
        AttributionField::SourceArtist => "source_artist",
        AttributionField::StemType => "stem_type",
        AttributionField::TimeRange => "time_range",
        AttributionField::RightsStatus => "rights",
    }
}

impl From<CliError> for ApiError {
    fn from(e: CliError) -> Self {
        match e {
            // A missing entity → 404. The client maps any 404 to `NotFoundError(path)`.
            CliError::NotFound(msg) => ApiError::not_found(msg),

            // The attribution gate → 422 with the typed missing-field list. The gate runs BEFORE any
            // write, so by contract nothing was created when this is returned.
            CliError::IncompleteAttribution(inc) => ApiError {
                status: StatusCode::UNPROCESSABLE_ENTITY,
                body: ApiErrorBody::IncompleteAttribution {
                    missing: inc
                        .missing
                        .into_iter()
                        .map(attribution_field_wire)
                        .collect(),
                },
            },

            // A slice past the stem's length (SAMP-05) — also creates nothing. 422 with a plain
            // message (NO `error` tag), so the client treats it as a generic `ApiError`, not the
            // incomplete-attribution branch.
            CliError::SampleOutOfRange(msg) => {
                ApiError::new(StatusCode::UNPROCESSABLE_ENTITY, msg)
            }

            // Backpressure from the durable queue is transient — 503 invites a retry.
            CliError::Job(JobError::Full) => {
                ApiError::new(StatusCode::SERVICE_UNAVAILABLE, "job queue is full; retry shortly")
            }

            // Everything else is an unexpected server-side failure → 500.
            CliError::Job(err) => ApiError::internal(format!("job queue error: {err}")),
            CliError::Store(err) => ApiError::internal(format!("object store error: {err}")),
            CliError::Repo(err) => ApiError::internal(format!("repository error: {err}")),
            CliError::ReadFile { .. } => {
                // Not reachable over HTTP (bytes arrive via multipart, never a path), but mapped for
                // exhaustiveness so a future code path cannot silently drop it.
                ApiError::internal("internal read error")
            }
            CliError::Config(msg) => ApiError::internal(format!("configuration error: {msg}")),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        match self.body {
            ApiErrorBody::Message(message) => {
                (self.status, Json(MessageBody { message })).into_response()
            }
            ApiErrorBody::IncompleteAttribution { missing } => (
                self.status,
                Json(IncompleteAttributionBody {
                    error: "incomplete_attribution",
                    missing,
                }),
            )
                .into_response(),
        }
    }
}

#[derive(Serialize)]
struct MessageBody {
    message: String,
}

#[derive(Serialize)]
struct IncompleteAttributionBody {
    error: &'static str,
    missing: Vec<&'static str>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::attribution::IncompleteAttribution;

    /// Pin every wire spelling against the TS `AttributionField` union (`web/src/api/types.ts`).
    /// This is the guard for the deliberate `source_artist`/`rights` divergence from the CLI's
    /// `AttributionField::as_str()` ("artist"/"rights") and the serde rename ("rights_status").
    #[test]
    fn attribution_field_wire_matches_ts_union() {
        use AttributionField::*;
        assert_eq!(attribution_field_wire(SourceTrack), "source_track");
        assert_eq!(attribution_field_wire(Stem), "stem");
        assert_eq!(attribution_field_wire(SourceTitle), "source_title");
        assert_eq!(attribution_field_wire(SourceArtist), "source_artist");
        assert_eq!(attribution_field_wire(StemType), "stem_type");
        assert_eq!(attribution_field_wire(TimeRange), "time_range");
        assert_eq!(attribution_field_wire(RightsStatus), "rights");
    }

    #[test]
    fn not_found_maps_to_404() {
        let api: ApiError = CliError::NotFound("fragment x".into()).into();
        assert_eq!(api.status, StatusCode::NOT_FOUND);
        assert!(matches!(api.body, ApiErrorBody::Message(_)));
    }

    #[test]
    fn incomplete_attribution_maps_to_422_with_typed_missing() {
        let inc = IncompleteAttribution {
            missing: vec![AttributionField::SourceArtist, AttributionField::RightsStatus],
        };
        let api: ApiError = CliError::IncompleteAttribution(inc).into();
        assert_eq!(api.status, StatusCode::UNPROCESSABLE_ENTITY);
        match api.body {
            // The wire names — NOT "artist"/"rights_status".
            ApiErrorBody::IncompleteAttribution { missing } => {
                assert_eq!(missing, vec!["source_artist", "rights"]);
            }
            other => panic!("expected IncompleteAttribution body, got {other:?}"),
        }
    }

    #[test]
    fn sample_out_of_range_maps_to_422_message_without_error_tag() {
        let api: ApiError = CliError::SampleOutOfRange("slice past stem".into()).into();
        assert_eq!(api.status, StatusCode::UNPROCESSABLE_ENTITY);
        // A plain message (no `error` tag) so the client treats it as a generic ApiError, never the
        // incomplete-attribution branch.
        assert!(matches!(api.body, ApiErrorBody::Message(_)));
    }

    #[test]
    fn job_full_maps_to_503() {
        let api: ApiError = CliError::Job(JobError::Full).into();
        assert_eq!(api.status, StatusCode::SERVICE_UNAVAILABLE);
    }
}
