//! The axum handlers — one per endpoint in `web/src/api/HttpNamelessApi.ts`.
//!
//! Every handler is the same thin shape:
//!   1. parse the request (path params, query, JSON body, or multipart) in the ASYNC context;
//!   2. clone the `Arc<Plane>` and run the SYNCHRONOUS control-plane use-case inside
//!      [`tokio::task::spawn_blocking`] — the ports are sync and the Postgres adapter `block_on`s
//!      internally, so calling them directly on a Tokio worker thread could starve the runtime (and
//!      `block_on` inside a runtime worker panics). `spawn_blocking` moves that work to the blocking
//!      pool, which is exactly what it is for;
//!   3. map the domain result to a wire DTO ([`crate::dto`]) and the error to an [`ApiError`].
//!
//! The integrity logic (the attribution gate, content-hashing, probing, enqueueing, the rollback on
//! a failed multi-store write) lives entirely in the reused `do_*` use-cases — this layer never
//! re-implements it. Project-existence 404s are added here to match the web `MockNamelessApi`
//! (`requireProject`), which the UI was written and tested against.

use axum::extract::{Multipart, Path, Query, State};
use axum::Json;
use serde::Deserialize;
use uuid::Uuid;

use nameless_cli::cli::{
    do_capture_bytes, do_create_project, do_reference_upload_bytes, do_sample_add,
    do_stems_separate, SampleAddArgs,
};
use nameless_cli::error::CliError;
use nameless_core::attribution::RightsStatus;
use nameless_core::fragment::{FragmentId, FragmentKind, ProjectId};
use nameless_core::reference::{ReferenceRole, ReferenceTrackId};
use nameless_core::stems::StemId;

use crate::dto::{
    build_project_graph, AttachReferenceResultDto, CaptureResultDto, CreditsDto, FragmentDetailDto,
    FragmentSummaryDto, ProjectDto, ProjectGraphDto, ReferenceListItemDto, ReferenceUploadResultDto,
    ReferenceViewDto, SampleAddResultDto, SampleViewDto, SeparateStemsResultDto, StemSummaryDto,
};
use crate::error::ApiError;
use crate::state::AppState;

/// Run a synchronous control-plane closure on the blocking pool and fold both the join error and the
/// [`CliError`] into an [`ApiError`]. The closure owns its captured `Arc<Plane>` + request data, so
/// it is `Send + 'static` as `spawn_blocking` requires.
async fn run_blocking<T, F>(f: F) -> Result<T, ApiError>
where
    F: FnOnce() -> Result<T, CliError> + Send + 'static,
    T: Send + 'static,
{
    match tokio::task::spawn_blocking(f).await {
        Ok(result) => result.map_err(ApiError::from),
        Err(join_err) => Err(ApiError::internal(format!("task join error: {join_err}"))),
    }
}

// =================================================================================================
// Projects
// =================================================================================================

/// `GET /projects` — all projects (newest-first).
pub async fn list_projects(State(st): State<AppState>) -> Result<Json<Vec<ProjectDto>>, ApiError> {
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        let projects = plane.repo.list_projects()?;
        Ok(projects.iter().map(ProjectDto::from_domain).collect::<Vec<_>>())
    })
    .await?;
    Ok(Json(dto))
}

/// The body of `POST /projects`.
#[derive(Debug, Deserialize)]
pub struct CreateProjectBody {
    pub title: String,
}

/// `POST /projects` — create a project. A blank/whitespace title is a 400 (parity with the mock).
pub async fn create_project(
    State(st): State<AppState>,
    Json(body): Json<CreateProjectBody>,
) -> Result<Json<ProjectDto>, ApiError> {
    let title = body.title.trim().to_string();
    if title.is_empty() {
        return Err(ApiError::bad_request("project title is required"));
    }
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        let project = do_create_project(&plane, title)?;
        Ok(ProjectDto::from_domain(&project))
    })
    .await?;
    Ok(Json(dto))
}

// =================================================================================================
// Capture (UI-01)
// =================================================================================================

struct CaptureForm {
    note: String,
    kind: FragmentKind,
    bytes: Vec<u8>,
}

/// Read the capture multipart: `note` (text), `kind` (text, defaults to `hook`), `file` (bytes).
async fn read_capture_multipart(mut mp: Multipart) -> Result<CaptureForm, ApiError> {
    let mut note: Option<String> = None;
    let mut kind = FragmentKind::Hook; // matches the CLI's `--kind` default
    let mut bytes: Option<Vec<u8>> = None;

    while let Some(field) = mp
        .next_field()
        .await
        .map_err(|e| ApiError::bad_request(format!("invalid multipart body: {e}")))?
    {
        // Own the field name first so the borrow does not outlive the consuming `text()`/`bytes()`.
        let name = field.name().map(str::to_string);
        match name.as_deref() {
            Some("note") => {
                note = Some(field.text().await.map_err(field_err("note"))?);
            }
            Some("kind") => {
                let raw = field.text().await.map_err(field_err("kind"))?;
                kind = FragmentKind::from_db_str(&raw)
                    .ok_or_else(|| ApiError::bad_request(format!("unknown fragment kind: {raw:?}")))?;
            }
            Some("file") => {
                let data = field.bytes().await.map_err(field_err("file"))?;
                bytes = Some(data.to_vec());
            }
            // Drain any unexpected field so the stream stays well-formed.
            _ => {
                let _ = field.bytes().await;
            }
        }
    }

    Ok(CaptureForm {
        note: note.ok_or_else(|| ApiError::bad_request("missing `note` field"))?,
        kind,
        bytes: bytes.ok_or_else(|| ApiError::bad_request("missing `file` field"))?,
    })
}

/// `POST /projects/:id/fragments` (multipart) — capture a fragment + intent note.
pub async fn capture(
    State(st): State<AppState>,
    Path(project): Path<Uuid>,
    multipart: Multipart,
) -> Result<Json<CaptureResultDto>, ApiError> {
    let project = ProjectId(project);
    let form = read_capture_multipart(multipart).await?;
    if form.note.trim().is_empty() {
        return Err(ApiError::bad_request("an intent note is required"));
    }
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        // 404 the unknown project before storing anything (parity with the mock's requireProject).
        if plane.repo.get_project(project)?.is_none() {
            return Err(CliError::NotFound(format!("project {project}")));
        }
        let (frag, job) = do_capture_bytes(&plane, project, form.kind, form.note, &form.bytes)?;
        Ok(CaptureResultDto::from_domain(&frag, job))
    })
    .await?;
    Ok(Json(dto))
}

/// The optional `?project=<uuid>` filter on `GET /fragments`.
#[derive(Debug, Deserialize)]
pub struct ListFragmentsQuery {
    pub project: Option<Uuid>,
}

/// `GET /fragments?project=:id` — list fragments, optionally scoped to a project.
pub async fn list_fragments(
    State(st): State<AppState>,
    Query(q): Query<ListFragmentsQuery>,
) -> Result<Json<Vec<FragmentSummaryDto>>, ApiError> {
    let project = q.project.map(ProjectId);
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        let frags = plane.repo.list_fragments(project)?;
        Ok(frags.iter().map(FragmentSummaryDto::from_domain).collect::<Vec<_>>())
    })
    .await?;
    Ok(Json(dto))
}

/// `GET /fragments/:id` — a single fragment's compact summary.
pub async fn get_fragment(
    State(st): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<FragmentDetailDto>, ApiError> {
    let id = FragmentId(id);
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        let f = plane
            .repo
            .get_fragment(id)?
            .ok_or_else(|| CliError::NotFound(format!("fragment {id}")))?;
        Ok(FragmentDetailDto::from_domain(&f))
    })
    .await?;
    Ok(Json(dto))
}

// =================================================================================================
// Reference (UI-02)
// =================================================================================================

/// `GET /references` — all uploaded references (with their analyzed flag).
pub async fn list_references(
    State(st): State<AppState>,
) -> Result<Json<Vec<ReferenceListItemDto>>, ApiError> {
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        let tracks = plane.references.list_tracks()?;
        let mut out = Vec::with_capacity(tracks.len());
        for t in &tracks {
            let analyzed = plane.references.get_context_summary(t.id)?.is_some();
            out.push(ReferenceListItemDto::from_domain(t, analyzed));
        }
        Ok(out)
    })
    .await?;
    Ok(Json(dto))
}

struct ReferenceForm {
    title: Option<String>,
    artist: Option<String>,
    bytes: Vec<u8>,
}

/// Read the reference-upload multipart: optional `title`/`artist` (text) + `file` (bytes).
async fn read_reference_multipart(mut mp: Multipart) -> Result<ReferenceForm, ApiError> {
    let mut title: Option<String> = None;
    let mut artist: Option<String> = None;
    let mut bytes: Option<Vec<u8>> = None;

    while let Some(field) = mp
        .next_field()
        .await
        .map_err(|e| ApiError::bad_request(format!("invalid multipart body: {e}")))?
    {
        let name = field.name().map(str::to_string);
        match name.as_deref() {
            Some("title") => title = Some(field.text().await.map_err(field_err("title"))?),
            Some("artist") => artist = Some(field.text().await.map_err(field_err("artist"))?),
            Some("file") => bytes = Some(field.bytes().await.map_err(field_err("file"))?.to_vec()),
            _ => {
                let _ = field.bytes().await;
            }
        }
    }

    Ok(ReferenceForm {
        title,
        artist,
        bytes: bytes.ok_or_else(|| ApiError::bad_request("missing `file` field"))?,
    })
}

/// `POST /references` (multipart) — upload a finished reference track.
pub async fn upload_reference(
    State(st): State<AppState>,
    multipart: Multipart,
) -> Result<Json<ReferenceUploadResultDto>, ApiError> {
    let form = read_reference_multipart(multipart).await?;
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        let (track, job) = do_reference_upload_bytes(&plane, form.title, form.artist, &form.bytes)?;
        Ok(ReferenceUploadResultDto::from_domain(&track, job))
    })
    .await?;
    Ok(Json(dto))
}

/// `GET /references/:id` — a reference's compact vibe/target summary (analysis null until analyzed).
pub async fn get_reference(
    State(st): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<ReferenceViewDto>, ApiError> {
    let id = ReferenceTrackId(id);
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        let track = plane
            .references
            .get_track(id)?
            .ok_or_else(|| CliError::NotFound(format!("reference {id}")))?;
        let summary = plane.references.get_context_summary(id)?;
        Ok(ReferenceViewDto::from_domain(&track, summary.as_ref()))
    })
    .await?;
    Ok(Json(dto))
}

/// The body of `POST /projects/:id/references` — snake_case to match the Rust serde contract.
#[derive(Debug, Deserialize)]
pub struct AttachReferenceBody {
    pub reference_id: Uuid,
    pub role: ReferenceRole,
}

/// `POST /projects/:id/references` — attach a reference to a project as conditioning.
pub async fn attach_reference(
    State(st): State<AppState>,
    Path(project): Path<Uuid>,
    Json(body): Json<AttachReferenceBody>,
) -> Result<Json<AttachReferenceResultDto>, ApiError> {
    let project = ProjectId(project);
    let reference = ReferenceTrackId(body.reference_id);
    let role = body.role;
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        // Match the mock: the reference, then the project, must exist (both 404).
        if plane.references.get_track(reference)?.is_none() {
            return Err(CliError::NotFound(format!("reference {reference}")));
        }
        if plane.repo.get_project(project)?.is_none() {
            return Err(CliError::NotFound(format!("project {project}")));
        }
        plane.references.attach(project, reference, role)?;
        Ok(AttachReferenceResultDto {
            reference: reference.0,
            project: project.0,
            role,
        })
    })
    .await?;
    Ok(Json(dto))
}

// =================================================================================================
// Stem library + sampling (UI-03)
// =================================================================================================

/// `POST /tracks/:id/stems/separate` — enqueue stem separation for a track (404 on unknown track).
pub async fn separate_stems(
    State(st): State<AppState>,
    Path(track): Path<Uuid>,
) -> Result<Json<SeparateStemsResultDto>, ApiError> {
    let track = ReferenceTrackId(track);
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        // `do_stems_separate` already 404s an unknown track and enqueues exactly one SeparateTrack job.
        let job = do_stems_separate(&plane, track)?;
        Ok(SeparateStemsResultDto {
            reference: track.0,
            enqueued_job: job.0,
        })
    })
    .await?;
    Ok(Json(dto))
}

/// `GET /tracks/:id/stems` — the retained stems of a track (404 on unknown track, per the mock).
pub async fn list_stems(
    State(st): State<AppState>,
    Path(track): Path<Uuid>,
) -> Result<Json<Vec<StemSummaryDto>>, ApiError> {
    let track = ReferenceTrackId(track);
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        if plane.references.get_track(track)?.is_none() {
            return Err(CliError::NotFound(format!("reference {track}")));
        }
        let stems = plane.samples.list_stems(track)?;
        Ok(stems.iter().map(StemSummaryDto::from_domain).collect::<Vec<_>>())
    })
    .await?;
    Ok(Json(dto))
}

/// The body of `POST /projects/:id/samples` — snake_case to match the Rust attribution contract.
#[derive(Debug, Deserialize)]
pub struct AddSampleBody {
    pub stem_id: Uuid,
    pub source_artist: String,
    /// Falls back to the source track's title when omitted (as the CLI/mock do).
    #[serde(default)]
    pub source_title: Option<String>,
    pub start_ms: u32,
    pub end_ms: u32,
    pub rights: RightsStatus,
}

/// `POST /projects/:id/samples` — promote a stem to a `sampled` fragment with COMPLETE attribution.
///
/// The hard gate lives in the reused `do_sample_add`: an incomplete attribution returns
/// `CliError::IncompleteAttribution` (→ 422 `{"error":"incomplete_attribution","missing":[…]}`) and
/// NOTHING is created (the validation precedes every write, and any post-write failure compensates).
pub async fn add_sample(
    State(st): State<AppState>,
    Path(project): Path<Uuid>,
    Json(body): Json<AddSampleBody>,
) -> Result<Json<SampleAddResultDto>, ApiError> {
    let project = ProjectId(project);
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        // 404 an unknown project before the gate (parity with the mock's requireProject).
        if plane.repo.get_project(project)?.is_none() {
            return Err(CliError::NotFound(format!("project {project}")));
        }
        let args = SampleAddArgs {
            stem: StemId(body.stem_id),
            project,
            artist: body.source_artist,
            time_range: (body.start_ms, body.end_ms),
            rights: body.rights.into(),
            title: body.source_title,
        };
        let (frag, attr, job) = do_sample_add(&plane, &args)?;
        Ok(SampleAddResultDto::from_domain(&frag, &attr, job))
    })
    .await?;
    Ok(Json(dto))
}

/// `GET /samples/:fragmentId` — a sampled fragment's attribution + rights status.
pub async fn get_sample(
    State(st): State<AppState>,
    Path(fragment): Path<Uuid>,
) -> Result<Json<SampleViewDto>, ApiError> {
    let fragment = FragmentId(fragment);
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        let attr = plane
            .samples
            .get_attribution(fragment)?
            .ok_or_else(|| CliError::NotFound(format!("sample attribution for fragment {fragment}")))?;
        Ok(SampleViewDto::from_domain(&attr))
    })
    .await?;
    Ok(Json(dto))
}

// =================================================================================================
// Project graph + credits (UI-04)
// =================================================================================================

/// `GET /projects/:id/graph` — the fragment graph (nodes + lineage edges).
pub async fn project_graph(
    State(st): State<AppState>,
    Path(project): Path<Uuid>,
) -> Result<Json<ProjectGraphDto>, ApiError> {
    let project = ProjectId(project);
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        if plane.repo.get_project(project)?.is_none() {
            return Err(CliError::NotFound(format!("project {project}")));
        }
        let frags = plane.repo.list_fragments(Some(project))?;
        Ok(build_project_graph(project.0, &frags))
    })
    .await?;
    Ok(Json(dto))
}

/// `GET /projects/:id/credits` — the project's sample credits sheet.
pub async fn get_credits(
    State(st): State<AppState>,
    Path(project): Path<Uuid>,
) -> Result<Json<CreditsDto>, ApiError> {
    let project = ProjectId(project);
    let plane = st.plane.clone();
    let dto = run_blocking(move || {
        // The credits header uses the real project title (the mock does too); 404 if it is unknown.
        let p = plane
            .repo
            .get_project(project)?
            .ok_or_else(|| CliError::NotFound(format!("project {project}")))?;
        let rows = plane.samples.list_project_attributions(project)?;
        Ok(CreditsDto::from_domain(&p.title, &rows))
    })
    .await?;
    Ok(Json(dto))
}

/// Helper: turn a multipart field-read error into a 400 naming the offending field.
fn field_err(field: &'static str) -> impl Fn(axum::extract::multipart::MultipartError) -> ApiError {
    move |e| ApiError::bad_request(format!("invalid `{field}` field: {e}"))
}
