//! The `nameless` command tree (clap derive) + the command handlers.
//!
//! Subcommands (Phase 1): `project create`, `capture`, `fragments list`, `fragments show`.
//! Global flags: `--local` (filesystem + in-memory profile, no Postgres) and `--json` (machine
//! output). The capture handler is the walking skeleton: read → content-hash → store → probe →
//! persist fragment → enqueue a FeatureExtract job — all behind the core ports.

use std::fs;
use std::path::PathBuf;

use clap::{Args, Parser, Subcommand, ValueEnum};
use uuid::Uuid;

use nameless_core::attribution::{
    PartialAttribution, RightsStatus, SampleAttribution,
};
use nameless_core::fragment::{Fragment, FragmentId, FragmentKind, Project, ProjectId};
use nameless_core::job::{JobEnvelope, JobId};
use nameless_core::reference::{ReferenceRole, ReferenceTrack, ReferenceTrackId};
use nameless_core::stems::{Stem, StemId};
use nameless_adapters::{content_hash, probe};

use crate::error::CliError;
use crate::output;
use crate::profile::{build_plane, Plane};

/// `nameless` — capture musical fragments into a typed, durable graph.
#[derive(Debug, Parser)]
#[command(name = "nameless", version, about = "Nameless control-plane CLI", long_about = None)]
pub struct Cli {
    /// Use the local profile: filesystem object store + JSON file repo + in-memory queue (no Postgres).
    #[arg(long, global = true)]
    pub local: bool,

    /// Emit machine-readable JSON instead of compact human output.
    #[arg(long, global = true)]
    pub json: bool,

    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub enum Command {
    /// Project operations.
    Project {
        #[command(subcommand)]
        action: ProjectAction,
    },
    /// Capture an audio fragment with an intent note into a project.
    Capture(CaptureArgs),
    /// Inspect captured fragments.
    Fragments {
        #[command(subcommand)]
        action: FragmentsAction,
    },
    /// Reference-track context: upload a finished song for vibe + non-melodic sonic targets,
    /// inspect its summary, and attach it to a project as conditioning (never to clone it).
    Reference {
        #[command(subcommand)]
        action: ReferenceAction,
    },
    /// Stem library: separate an uploaded track into retained stems and browse them (Phase 8).
    Stems {
        #[command(subcommand)]
        action: StemsAction,
    },
    /// Attributed sampling: promote a stem to a `sampled` fragment with complete attribution,
    /// or show a sample's attribution + rights status (attribution is NOT permission).
    Sample {
        #[command(subcommand)]
        action: SampleAction,
    },
    /// Generate a project's credits sheet from its sample attributions (SAMP-05).
    Credits {
        /// The project UUID to render credits for.
        #[arg(value_parser = parse_project_id)]
        project: ProjectId,
    },
}

#[derive(Debug, Subcommand)]
pub enum ProjectAction {
    /// Create a new project.
    Create {
        /// Human title for the project.
        #[arg(long)]
        title: String,
    },
}

#[derive(Debug, Args)]
pub struct CaptureArgs {
    /// Path to the audio file to capture (wav/mp3/flac/m4a).
    pub path: PathBuf,
    /// The intent note — what this fragment is for ("chorus hook, over the 2nd drop").
    #[arg(long)]
    pub note: String,
    /// The project UUID to capture into.
    #[arg(long, value_parser = parse_project_id)]
    pub project: ProjectId,
    /// The kind of material (default: hook).
    #[arg(long, value_enum, default_value_t = KindArg::Hook)]
    pub kind: KindArg,
}

#[derive(Debug, Subcommand)]
pub enum FragmentsAction {
    /// List fragments, optionally filtered to one project.
    List {
        #[arg(long, value_parser = parse_project_id)]
        project: Option<ProjectId>,
    },
    /// Show a single fragment's compact summary.
    Show {
        #[arg(value_parser = parse_fragment_id)]
        id: FragmentId,
    },
}

#[derive(Debug, Subcommand)]
pub enum ReferenceAction {
    /// Upload a finished reference track. Stores the audio immutably by content hash and enqueues a
    /// non-melodic context-extraction job (CLAP style embedding + genre + tempo range + LUFS +
    /// tonal balance + stereo width + vibe). The reference is NOT a fragment and never enters the
    /// arrangement (REF-01/REF-03).
    Upload(ReferenceUploadArgs),
    /// Show a reference's compact vibe/target summary (never the embedding vector or any array).
    Show {
        #[arg(value_parser = parse_reference_id)]
        id: ReferenceTrackId,
    },
    /// Attach a reference to a project as conditioning context (REF-04).
    Attach {
        #[arg(value_parser = parse_reference_id)]
        id: ReferenceTrackId,
        /// The project UUID to attach the reference to.
        #[arg(long, value_parser = parse_project_id)]
        project: ProjectId,
        /// What the reference steers: `vibe` (atmosphere) or `sonic-target` (measurable numbers).
        #[arg(long, value_enum, default_value_t = RoleArg::Vibe)]
        role: RoleArg,
    },
}

#[derive(Debug, Args)]
pub struct ReferenceUploadArgs {
    /// Path to the finished audio file to upload (wav/mp3/flac/m4a).
    pub path: PathBuf,
    /// Optional track title (for the credits sheet / UI; never used as a conditioning target).
    #[arg(long)]
    pub title: Option<String>,
    /// Optional artist (credits / UI only).
    #[arg(long)]
    pub artist: Option<String>,
}

#[derive(Debug, Subcommand)]
pub enum StemsAction {
    /// Separate an uploaded reference track into its retained stem library (enqueues a Demucs job
    /// for the Python worker). Any uploaded track can be separated, any time (SAMP-01).
    Separate {
        #[arg(value_parser = parse_reference_id)]
        track: ReferenceTrackId,
    },
    /// List the retained stems of an uploaded track (browsable indefinitely).
    List {
        #[arg(value_parser = parse_reference_id)]
        track: ReferenceTrackId,
    },
}

#[derive(Debug, Subcommand)]
pub enum SampleAction {
    /// Promote a library stem to a `sampled` fragment with COMPLETE attribution (SAMP-02/03).
    /// Validation is a hard gate: a missing artist / time-range / rights / title is rejected with
    /// the exact list of what is missing — an incompletely-attributed sample cannot be created.
    Add(SampleAddArgs),
    /// Show a sampled fragment's attribution + rights status (states attribution ≠ permission).
    Show {
        #[arg(value_parser = parse_fragment_id)]
        fragment: FragmentId,
    },
}

#[derive(Debug, Args)]
pub struct SampleAddArgs {
    /// The stem UUID to promote (from `stems list <track>`).
    #[arg(value_parser = parse_stem_id)]
    pub stem: StemId,
    /// The project to add the sampled fragment to.
    #[arg(long, value_parser = parse_project_id)]
    pub project: ProjectId,
    /// The source artist (required for a complete credit).
    #[arg(long)]
    pub artist: String,
    /// The slice used, in milliseconds: `START-END` (e.g. `12000-18000`). `END` must exceed `START`.
    #[arg(long, value_parser = parse_time_range)]
    pub time_range: (u32, u32),
    /// The rights/clearance status of the source (attribution is NOT permission).
    #[arg(long, value_enum)]
    pub rights: RightsArg,
    /// The source title. Defaults to the uploaded track's title if it has one.
    #[arg(long)]
    pub title: Option<String>,
}

/// clap value-enum mirror of [`RightsStatus`] for `--rights`.
#[derive(Debug, Clone, Copy, ValueEnum)]
#[clap(rename_all = "kebab-case")]
pub enum RightsArg {
    CopyrightedUncleared,
    RoyaltyFree,
    OwnWork,
    Unknown,
}

impl From<RightsArg> for RightsStatus {
    fn from(r: RightsArg) -> Self {
        match r {
            RightsArg::CopyrightedUncleared => RightsStatus::CopyrightedUncleared,
            RightsArg::RoyaltyFree => RightsStatus::RoyaltyFree,
            RightsArg::OwnWork => RightsStatus::OwnWork,
            RightsArg::Unknown => RightsStatus::Unknown,
        }
    }
}

impl From<RightsStatus> for RightsArg {
    /// The reverse mapping (Phase 10): the HTTP API receives a `rights` value already typed as the
    /// domain [`RightsStatus`] (serde-deserialized from the request body) and needs to hand
    /// [`SampleAddArgs`] — the shared `do_sample_add` input — a [`RightsArg`]. Lives here, beside the
    /// forward conversion, so both halves of the mapping stay in one place.
    fn from(r: RightsStatus) -> Self {
        match r {
            RightsStatus::CopyrightedUncleared => RightsArg::CopyrightedUncleared,
            RightsStatus::RoyaltyFree => RightsArg::RoyaltyFree,
            RightsStatus::OwnWork => RightsArg::OwnWork,
            RightsStatus::Unknown => RightsArg::Unknown,
        }
    }
}

/// clap value-enum mirror of [`ReferenceRole`] for `--role` (accepts `vibe` / `sonic-target`).
#[derive(Debug, Clone, Copy, ValueEnum)]
#[clap(rename_all = "kebab-case")]
pub enum RoleArg {
    Vibe,
    SonicTarget,
}

impl From<RoleArg> for ReferenceRole {
    fn from(r: RoleArg) -> Self {
        match r {
            RoleArg::Vibe => ReferenceRole::Vibe,
            RoleArg::SonicTarget => ReferenceRole::SonicTarget,
        }
    }
}

/// clap value-enum mirror of [`FragmentKind`] for `--kind`.
#[derive(Debug, Clone, Copy, ValueEnum)]
#[clap(rename_all = "snake_case")]
pub enum KindArg {
    Melody,
    Hook,
    Beat,
    Rhythm,
    Chord,
    Pad,
    Adlib,
    Stem,
    Full,
}

impl From<KindArg> for FragmentKind {
    fn from(k: KindArg) -> Self {
        match k {
            KindArg::Melody => FragmentKind::Melody,
            KindArg::Hook => FragmentKind::Hook,
            KindArg::Beat => FragmentKind::Beat,
            KindArg::Rhythm => FragmentKind::Rhythm,
            KindArg::Chord => FragmentKind::Chord,
            KindArg::Pad => FragmentKind::Pad,
            KindArg::Adlib => FragmentKind::Adlib,
            KindArg::Stem => FragmentKind::Stem,
            KindArg::Full => FragmentKind::Full,
        }
    }
}

fn parse_project_id(s: &str) -> Result<ProjectId, String> {
    Uuid::parse_str(s)
        .map(ProjectId)
        .map_err(|_| format!("invalid project UUID: {s:?}"))
}

fn parse_fragment_id(s: &str) -> Result<FragmentId, String> {
    Uuid::parse_str(s)
        .map(FragmentId)
        .map_err(|_| format!("invalid fragment UUID: {s:?}"))
}

fn parse_reference_id(s: &str) -> Result<ReferenceTrackId, String> {
    Uuid::parse_str(s)
        .map(ReferenceTrackId)
        .map_err(|_| format!("invalid reference UUID: {s:?}"))
}

fn parse_stem_id(s: &str) -> Result<StemId, String> {
    Uuid::parse_str(s)
        .map(StemId)
        .map_err(|_| format!("invalid stem UUID: {s:?}"))
}

/// Parse `--time-range START-END` (milliseconds) into `(start, end)` with `end > start`.
fn parse_time_range(s: &str) -> Result<(u32, u32), String> {
    let (start, end) = s
        .split_once('-')
        .ok_or_else(|| format!("time range must be START-END in ms, got {s:?}"))?;
    let start: u32 = start
        .trim()
        .parse()
        .map_err(|_| format!("invalid start ms: {start:?}"))?;
    let end: u32 = end
        .trim()
        .parse()
        .map_err(|_| format!("invalid end ms: {end:?}"))?;
    if end <= start {
        return Err(format!("end ({end}) must exceed start ({start})"));
    }
    Ok((start, end))
}

/// Top-level dispatch. Builds the [`Plane`] from flags then runs the subcommand.
pub fn run(cli: Cli) -> Result<(), CliError> {
    let plane = build_plane(cli.local)?;
    match cli.command {
        Command::Project { action } => match action {
            ProjectAction::Create { title } => {
                let project = do_create_project(&plane, title)?;
                output::print_project_created(&project, cli.json);
                Ok(())
            }
        },
        Command::Capture(args) => {
            let (frag, job) = do_capture(&plane, &args)?;
            output::print_capture(&frag, job, cli.json);
            Ok(())
        }
        Command::Fragments { action } => match action {
            FragmentsAction::List { project } => {
                let frags = plane.repo.list_fragments(project)?;
                output::print_fragment_list(&frags, cli.json);
                Ok(())
            }
            FragmentsAction::Show { id } => {
                let frag = plane
                    .repo
                    .get_fragment(id)?
                    .ok_or_else(|| CliError::NotFound(format!("fragment {id}")))?;
                output::print_fragment_show(&frag, cli.json);
                Ok(())
            }
        },
        Command::Reference { action } => match action {
            ReferenceAction::Upload(args) => {
                let (track, job) = do_reference_upload(&plane, &args)?;
                output::print_reference_uploaded(&track, job, cli.json);
                Ok(())
            }
            ReferenceAction::Show { id } => {
                let track = plane
                    .references
                    .get_track(id)?
                    .ok_or_else(|| CliError::NotFound(format!("reference {id}")))?;
                // None when uploaded but not yet analyzed — the summary is what `show` reports.
                let summary = plane.references.get_context_summary(id)?;
                output::print_reference_show(&track, summary.as_ref(), cli.json);
                Ok(())
            }
            ReferenceAction::Attach { id, project, role } => {
                // Fail clearly if the reference does not exist (mirrors fragment NotFound).
                if plane.references.get_track(id)?.is_none() {
                    return Err(CliError::NotFound(format!("reference {id}")));
                }
                let role: ReferenceRole = role.into();
                plane.references.attach(project, id, role)?;
                output::print_reference_attached(id, project, role, cli.json);
                Ok(())
            }
        },
        Command::Stems { action } => match action {
            StemsAction::Separate { track } => {
                let job = do_stems_separate(&plane, track)?;
                output::print_stems_separate(track, job, cli.json);
                Ok(())
            }
            StemsAction::List { track } => {
                let stems = plane.samples.list_stems(track)?;
                output::print_stem_list(&stems, cli.json);
                Ok(())
            }
        },
        Command::Sample { action } => match action {
            SampleAction::Add(args) => {
                let (frag, attr, job) = do_sample_add(&plane, &args)?;
                output::print_sample_added(&frag, &attr, job, cli.json);
                Ok(())
            }
            SampleAction::Show { fragment } => {
                let attr = plane
                    .samples
                    .get_attribution(fragment)?
                    .ok_or_else(|| CliError::NotFound(format!("sample attribution for fragment {fragment}")))?;
                output::print_sample_show(&attr, cli.json);
                Ok(())
            }
        },
        Command::Credits { project } => {
            let rows = plane.samples.list_project_attributions(project)?;
            // The credits header labels the project by id (the FragmentRepo port carries no title
            // lookup; the id is the stable, compact identifier the rest of the CLI prints anyway).
            output::print_credits(&project.to_string(), &rows, cli.json);
            Ok(())
        }
    }
}

/// Create a new project and persist it. Factored out (Phase 10) so both the CLI `project create`
/// handler and the HTTP `POST /projects` handler mint + insert a project the same way — there is no
/// integrity logic here, just the canonical `Project::new` constructor + the repo write, shared so
/// the two front-ends cannot drift. The caller is responsible for rejecting a blank title.
pub fn do_create_project(plane: &Plane, title: String) -> Result<Project, CliError> {
    let project = Project::new(title);
    plane.repo.insert_project(&project)?;
    Ok(project)
}

/// Enqueue stem separation for an uploaded reference track. Fails clearly if the track does not
/// exist. The Python `DemucsStemSeparator` consumes the job, retains every stem by content-hash, and
/// writes the `stems` index rows (SAMP-01).
pub fn do_stems_separate(plane: &Plane, track: ReferenceTrackId) -> Result<JobId, CliError> {
    if plane.references.get_track(track)?.is_none() {
        return Err(CliError::NotFound(format!("reference {track}")));
    }
    let job = plane.queue.enqueue(JobEnvelope::SeparateTrack {
        reference_track_id: track,
    })?;
    Ok(job)
}

/// Promote a library stem to a `sampled` fragment with COMPLETE attribution (SAMP-02/03).
///
/// The attribution-completeness invariant is enforced HERE, before anything is created: a
/// [`PartialAttribution`] is assembled from the resolved stem + the CLI flags, then validated with
/// [`PartialAttribution::into_complete`]. If anything is missing (e.g. no title and the source track
/// has none either), it returns [`CliError::IncompleteAttribution`] naming the missing fields and
/// **no fragment, attribution, or job is created** — incomplete-attribution promotion is impossible.
///
/// On success it: creates the `sampled` fragment (provenance `Sampled`, state `Captured`, audio =
/// the stem's content-hash), persists the complete attribution, and enqueues a `FeatureExtract` job
/// so the sample travels the human analysis path (Captured → Analyzing → Analyzed) like any capture.
/// The attribution then satisfies the placement gate when the fragment is later placed.
pub fn do_sample_add(
    plane: &Plane,
    args: &SampleAddArgs,
) -> Result<(Fragment, SampleAttribution, JobId), CliError> {
    // Resolve the stem (its reference_track_id + stem_type feed the attribution).
    let stem: Stem = plane
        .samples
        .get_stem(args.stem)?
        .ok_or_else(|| CliError::NotFound(format!("stem {}", args.stem)))?;

    // Title falls back to the uploaded track's title when not supplied on the CLI.
    let track = plane.references.get_track(stem.reference_track_id)?;
    let source_title = args
        .title
        .clone()
        .or_else(|| track.and_then(|t| t.title));

    let (start_ms, end_ms) = args.time_range;

    // SAMP-05: the slice must lie within the stem's known length — the credits sheet is the honesty
    // artifact and must never record a range the source does not contain. When `duration_ms` is known
    // (the separator may defer it; see IN-03), reject an out-of-range end with a clear error and
    // create nothing. (`parse_time_range` already guarantees `end_ms > start_ms`.)
    if let Some(stem_len) = stem.duration_ms {
        if end_ms > stem_len {
            return Err(CliError::SampleOutOfRange(format!(
                "time range {start_ms}-{end_ms} ms exceeds stem length {stem_len} ms (stem {})",
                stem.id
            )));
        }
    }

    let partial = PartialAttribution {
        source_track_id: Some(stem.reference_track_id),
        stem_id: Some(stem.id),
        source_title,
        source_artist: Some(args.artist.clone()),
        stem_type: Some(stem.stem_type),
        start_ms: Some(start_ms),
        end_ms: Some(end_ms),
        rights_status: Some(args.rights.into()),
    };

    // THE HARD GATE: validate completeness BEFORE creating anything (SAMP-03). The typed
    // `IncompleteAttribution` (its `missing: Vec<AttributionField>`) flows straight into `CliError`
    // so the HTTP layer can serialize the field names without re-deriving them.
    let complete = partial
        .into_complete()
        .map_err(CliError::IncompleteAttribution)?;

    // Create the sampled fragment. CONTRACT: the fragment's `audio_uri` points at the FULL stem, so
    // its `duration_ms` describes the full stem too (carried straight from the stem) — NOT the slice
    // length. The slice actually used lives solely in the attribution's [start_ms, end_ms) range, and
    // the M1 exporter trims to it at render time. (Setting `duration_ms` to the slice length here
    // would describe bytes the URI does not yet address — a latent trap for any consumer assuming
    // `duration_ms` matches `audio_uri`.)
    let note = format!(
        "sampled {} from {} — {}",
        complete.stem_type.as_str(),
        complete.source_title,
        complete.source_artist
    );
    let frag = Fragment::new_sampled(
        args.project,
        stem.audio_uri.clone(),
        stem.duration_ms,
        stem.sample_rate,
        note,
    );
    plane.repo.insert_fragment(&frag)?;

    // The next two writes (attribution, then job enqueue) hit different stores and are NOT in one
    // transaction (the file/in-memory profiles have no cross-store tx). A failure after the fragment
    // insert would otherwise orphan a `sampled` fragment with no attribution row (invisible to
    // `credits`) or with no analysis job. So on ANY failure here we COMPENSATE by deleting the
    // just-inserted fragment before returning the error — leaving the graph as if nothing happened.
    // (`delete_fragment` cascades to the attribution row on the Postgres profile, so even a partially
    // written attribution is cleaned up.)
    let attribution = SampleAttribution::new(frag.id, args.project, complete);
    if let Err(e) = plane.samples.insert_attribution(&attribution) {
        let _ = plane.repo.delete_fragment(frag.id);
        return Err(e.into());
    }

    // The sample travels the human analysis path — enqueue feature extraction (like capture).
    let job = match plane.queue.enqueue(JobEnvelope::FeatureExtract {
        fragment_id: frag.id,
    }) {
        Ok(job) => job,
        Err(e) => {
            // Roll back BOTH writes: drop the fragment (cascades to the attribution on Postgres;
            // the file/in-memory attribution row is keyed by fragment_id and is dropped explicitly).
            let _ = plane.samples.delete_attribution(frag.id);
            let _ = plane.repo.delete_fragment(frag.id);
            return Err(e.into());
        }
    };

    Ok((frag, attribution, job))
}

/// The reference-upload core, factored out so it can be unit-tested with injected in-memory
/// adapters. Stores the raw bytes immutably by content hash (de-duplicating; shared with capture +
/// the Phase-8 stem library), probes for duration/sample-rate, persists the `ReferenceTrack`, and
/// enqueues exactly one `AnalyzeReference` job. The track is NOT a fragment and never enters the
/// state machine (REF-01/REF-03). Returns the new track + the enqueued job id.
pub fn do_reference_upload(
    plane: &Plane,
    args: &ReferenceUploadArgs,
) -> Result<(ReferenceTrack, JobId), CliError> {
    let bytes = fs::read(&args.path).map_err(|source| CliError::ReadFile {
        path: args.path.display().to_string(),
        source,
    })?;
    do_reference_upload_bytes(plane, args.title.clone(), args.artist.clone(), &bytes)
}

/// The reference-upload core over raw BYTES — the transport-agnostic heart of `do_reference_upload`.
///
/// The CLI reaches this by reading a file path; the Phase-10 HTTP API reaches it with the bytes of a
/// multipart `file` part. Identical thereafter: content-address + store immutably (de-duplicating,
/// shared with capture + the stem library), probe for duration/sample-rate, persist the
/// `ReferenceTrack`, and enqueue exactly one `AnalyzeReference` job. The track is NOT a fragment and
/// never enters the state machine (REF-01/REF-03). Returns the new track + the enqueued job id.
pub fn do_reference_upload_bytes(
    plane: &Plane,
    title: Option<String>,
    artist: Option<String>,
    bytes: &[u8],
) -> Result<(ReferenceTrack, JobId), CliError> {
    // Content-address + store immutably (same path/contract as capture).
    let key = content_hash(bytes);
    plane.store.put(&key, bytes)?;

    let p = probe(bytes);

    let track = ReferenceTrack::new_upload(key, title, artist, p.duration_ms, p.sample_rate);
    plane.references.insert_track(&track)?;

    // Enqueue the NON-melodic context-extraction job (the Python restricted analyzer handles it).
    let job = plane
        .queue
        .enqueue(JobEnvelope::AnalyzeReference {
            reference_track_id: track.id,
        })?;

    Ok((track, job))
}

/// The capture core, factored out so it can be unit-tested with injected in-memory adapters.
///
/// Stores the raw bytes immutably by content hash, probes for duration/sample-rate, persists the
/// fragment (state `Captured`), and enqueues exactly one `FeatureExtract` job. Returns the new
/// fragment + the enqueued job id.
pub fn do_capture(plane: &Plane, args: &CaptureArgs) -> Result<(Fragment, JobId), CliError> {
    let bytes = fs::read(&args.path).map_err(|source| CliError::ReadFile {
        path: args.path.display().to_string(),
        source,
    })?;
    do_capture_bytes(
        plane,
        args.project,
        args.kind.into(),
        args.note.clone(),
        &bytes,
    )
}

/// The capture core over raw BYTES — the transport-agnostic heart of `do_capture`.
///
/// The CLI reaches this by reading a file path; the Phase-10 HTTP API reaches it with the bytes of a
/// multipart `file` part (`POST /projects/:id/fragments`). Identical thereafter: store the bytes
/// immutably by content hash (de-duplicating), probe for duration/sample-rate, persist the fragment
/// in `Captured` state, and enqueue exactly one `FeatureExtract` job. Returns the new fragment + the
/// enqueued job id. Does NOT check that `project` exists — the caller validates that (the CLI takes a
/// trusted id; the HTTP handler 404s first) so this core stays a pure write path.
pub fn do_capture_bytes(
    plane: &Plane,
    project: ProjectId,
    kind: FragmentKind,
    note: String,
    bytes: &[u8],
) -> Result<(Fragment, JobId), CliError> {
    // Content-address + store immutably (de-duplicating; same bytes → same uri).
    let key = content_hash(bytes);
    plane.store.put(&key, bytes)?;

    // Best-effort probe; capture stores the bytes regardless of probe success.
    let p = probe(bytes);

    let frag = Fragment::new_capture(project, kind, key, p.duration_ms, p.sample_rate, note);
    plane.repo.insert_fragment(&frag)?;

    // Enqueue downstream feature extraction (Phase 1 enqueues only — no consumer runs).
    let job = plane
        .queue
        .enqueue(JobEnvelope::FeatureExtract {
            fragment_id: frag.id,
        })?;

    Ok((frag, job))
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::job::{JobQueue, JobStatus};
    use nameless_core::ports::{AttributionStore, FragmentRepo, ReferenceStore, StemStore};
    use nameless_core::stems::StemType;
    use nameless_adapters::{
        InMemoryFragmentRepo, InMemoryJobQueue, InMemoryObjectStore, InMemoryReferenceStore,
        InMemorySampleStore,
    };
    use std::io::Write;

    fn valid_uuid() -> String {
        Uuid::new_v4().to_string()
    }

    // ---- clap parsing ----

    #[test]
    fn capture_parses_with_required_args() {
        let parsed = Cli::try_parse_from([
            "nameless",
            "--local",
            "capture",
            "hook.wav",
            "--note",
            "chorus hook",
            "--project",
            &valid_uuid(),
        ]);
        assert!(parsed.is_ok(), "expected capture to parse: {parsed:?}");
    }

    #[test]
    fn capture_missing_note_is_usage_error() {
        let parsed = Cli::try_parse_from([
            "nameless",
            "capture",
            "hook.wav",
            "--project",
            &valid_uuid(),
        ]);
        assert!(parsed.is_err());
    }

    #[test]
    fn capture_missing_project_is_usage_error() {
        let parsed =
            Cli::try_parse_from(["nameless", "capture", "hook.wav", "--note", "x"]);
        assert!(parsed.is_err());
    }

    #[test]
    fn capture_invalid_project_uuid_is_error() {
        let parsed = Cli::try_parse_from([
            "nameless",
            "capture",
            "hook.wav",
            "--note",
            "x",
            "--project",
            "not-a-uuid",
        ]);
        assert!(parsed.is_err());
    }

    #[test]
    fn fragments_show_requires_valid_uuid() {
        assert!(Cli::try_parse_from(["nameless", "fragments", "show", &valid_uuid()]).is_ok());
        assert!(Cli::try_parse_from(["nameless", "fragments", "show", "nope"]).is_err());
    }

    // ---- capture behavior (in-memory adapters) ----

    fn in_memory_plane() -> Plane {
        Plane {
            store: Box::new(InMemoryObjectStore::new()),
            repo: Box::new(InMemoryFragmentRepo::new()),
            queue: Box::new(InMemoryJobQueue::new(16)),
            references: Box::new(InMemoryReferenceStore::new()),
            samples: Box::new(InMemorySampleStore::new()),
        }
    }

    fn write_temp_bytes(tag: &str, bytes: &[u8]) -> PathBuf {
        let mut p = std::env::temp_dir();
        p.push(format!("nameless-cli-test-{tag}-{}.bin", Uuid::new_v4()));
        let mut f = fs::File::create(&p).unwrap();
        f.write_all(bytes).unwrap();
        p
    }

    #[test]
    fn capture_inserts_fragment_and_enqueues_one_feature_extract_job() {
        let plane = in_memory_plane();
        let project = ProjectId::new();
        let path = write_temp_bytes("cap", b"some audio-ish bytes");
        let args = CaptureArgs {
            path: path.clone(),
            note: "chorus hook".into(),
            project,
            kind: KindArg::Hook,
        };

        let (frag, job) = do_capture(&plane, &args).unwrap();

        // Fragment persisted in Captured state with the content-hash uri.
        let stored = plane.repo.get_fragment(frag.id).unwrap().unwrap();
        assert_eq!(stored.note_text, "chorus hook");
        assert_eq!(stored.state().as_str(), "captured");
        assert_eq!(stored.audio_uri, content_hash(b"some audio-ish bytes"));
        assert!(plane.store.exists(&stored.audio_uri).unwrap());

        // Exactly one FeatureExtract job, matching this fragment.
        let rec = plane.queue.consume().unwrap().expect("one job enqueued");
        assert_eq!(rec.id, job);
        match rec.envelope {
            JobEnvelope::FeatureExtract { fragment_id } => assert_eq!(fragment_id, frag.id),
            other => panic!("expected FeatureExtract, got {other:?}"),
        }
        // No second job; it remains Queued (no consumer runs in Phase 1 — we only peeked).
        assert!(plane.queue.consume().unwrap().is_none());
        assert!(matches!(rec.status, JobStatus::InProgress));

        let _ = fs::remove_file(&path);
    }

    #[test]
    fn same_bytes_capture_to_same_audio_uri() {
        let plane = in_memory_plane();
        let project = ProjectId::new();
        let path = write_temp_bytes("dedup", b"identical");
        let mk = |p: &PathBuf| CaptureArgs {
            path: p.clone(),
            note: "n".into(),
            project,
            kind: KindArg::Beat,
        };
        let (f1, _) = do_capture(&plane, &mk(&path)).unwrap();
        let (f2, _) = do_capture(&plane, &mk(&path)).unwrap();
        // Distinct fragment ids, identical content-hash uri (immutable + de-duplicating storage).
        assert_ne!(f1.id, f2.id);
        assert_eq!(f1.audio_uri, f2.audio_uri);
        let _ = fs::remove_file(&path);
    }

    // ---- reference subcommand parsing ----

    #[test]
    fn reference_upload_parses_with_optional_labels() {
        assert!(Cli::try_parse_from([
            "nameless", "--local", "reference", "upload", "song.wav", "--title", "Trust", "--artist",
            "Brent Faiyaz",
        ])
        .is_ok());
        // title/artist are optional.
        assert!(Cli::try_parse_from(["nameless", "reference", "upload", "song.wav"]).is_ok());
    }

    #[test]
    fn reference_attach_parses_role_kebab_and_requires_project() {
        let p = valid_uuid();
        let r = valid_uuid();
        assert!(Cli::try_parse_from([
            "nameless", "reference", "attach", &r, "--project", &p, "--role", "sonic-target",
        ])
        .is_ok());
        // role defaults to vibe; project is required.
        assert!(Cli::try_parse_from(["nameless", "reference", "attach", &r, "--project", &p]).is_ok());
        assert!(Cli::try_parse_from(["nameless", "reference", "attach", &r]).is_err());
    }

    #[test]
    fn reference_show_requires_valid_uuid() {
        assert!(Cli::try_parse_from(["nameless", "reference", "show", &valid_uuid()]).is_ok());
        assert!(Cli::try_parse_from(["nameless", "reference", "show", "nope"]).is_err());
    }

    // ---- reference upload behavior (in-memory adapters) ----

    #[test]
    fn upload_inserts_track_stores_audio_and_enqueues_one_analyze_job() {
        let plane = in_memory_plane();
        let path = write_temp_bytes("ref", b"finished song bytes");
        let args = ReferenceUploadArgs {
            path: path.clone(),
            title: Some("Trust".into()),
            artist: Some("Brent Faiyaz".into()),
        };

        let (track, job) = do_reference_upload(&plane, &args).unwrap();

        // Track persisted with the content-hash uri; audio stored.
        let stored = plane.references.get_track(track.id).unwrap().unwrap();
        assert_eq!(stored.audio_uri, content_hash(b"finished song bytes"));
        assert_eq!(stored.title.as_deref(), Some("Trust"));
        assert!(plane.store.exists(&stored.audio_uri).unwrap());

        // Exactly one AnalyzeReference job, matching this reference.
        let rec = plane.queue.consume().unwrap().expect("one job enqueued");
        assert_eq!(rec.id, job);
        match rec.envelope {
            JobEnvelope::AnalyzeReference { reference_track_id } => {
                assert_eq!(reference_track_id, track.id)
            }
            other => panic!("expected AnalyzeReference, got {other:?}"),
        }
        assert!(plane.queue.consume().unwrap().is_none());
        assert!(matches!(rec.status, JobStatus::InProgress));

        let _ = fs::remove_file(&path);
    }

    #[test]
    fn upload_then_attach_links_reference_to_project() {
        let plane = in_memory_plane();
        let path = write_temp_bytes("refattach", b"another finished song");
        let args = ReferenceUploadArgs {
            path: path.clone(),
            title: None,
            artist: None,
        };
        let (track, _) = do_reference_upload(&plane, &args).unwrap();

        let project = ProjectId::new();
        plane
            .references
            .attach(project, track.id, ReferenceRole::SonicTarget)
            .unwrap();

        let links = plane.references.list_project_references(project).unwrap();
        assert_eq!(links.len(), 1);
        assert_eq!(links[0].reference_track_id, track.id);
        assert_eq!(links[0].role, ReferenceRole::SonicTarget);

        let _ = fs::remove_file(&path);
    }

    // ---- Phase 8: stems / sample / credits ----

    #[test]
    fn time_range_parses_and_rejects_inverted() {
        assert_eq!(parse_time_range("12000-18000").unwrap(), (12_000, 18_000));
        assert!(parse_time_range("18000-12000").is_err()); // end <= start
        assert!(parse_time_range("12000").is_err()); // no dash
        assert!(parse_time_range("a-b").is_err());
    }

    #[test]
    fn sample_add_parses_required_flags_and_rights_kebab() {
        let stem = valid_uuid();
        let project = valid_uuid();
        assert!(Cli::try_parse_from([
            "nameless", "sample", "add", &stem, "--project", &project, "--artist", "Brent Faiyaz",
            "--time-range", "12000-18000", "--rights", "copyrighted-uncleared",
        ])
        .is_ok());
        // --rights and --artist and --time-range are required.
        assert!(Cli::try_parse_from(["nameless", "sample", "add", &stem, "--project", &project]).is_err());
    }

    #[test]
    fn stems_separate_enqueues_for_an_existing_track() {
        let plane = in_memory_plane();
        let track = ReferenceTrack::new_upload("trackhash".into(), Some("Trust".into()), None, None, None);
        plane.references.insert_track(&track).unwrap();

        let job = do_stems_separate(&plane, track.id).unwrap();
        let rec = plane.queue.consume().unwrap().expect("one job enqueued");
        assert_eq!(rec.id, job);
        match rec.envelope {
            JobEnvelope::SeparateTrack { reference_track_id } => assert_eq!(reference_track_id, track.id),
            other => panic!("expected SeparateTrack, got {other:?}"),
        }
    }

    #[test]
    fn stems_separate_unknown_track_is_not_found() {
        let plane = in_memory_plane();
        assert!(matches!(
            do_stems_separate(&plane, ReferenceTrackId::new()),
            Err(CliError::NotFound(_))
        ));
    }

    /// Seed a stem in the store the way the separation worker would, so `sample add` can promote it.
    fn seed_stem(plane: &Plane, track: ReferenceTrackId) -> Stem {
        let stem = Stem::new(
            track,
            StemType::Vocals,
            content_hash(b"vocal stem bytes"),
            "htdemucs_ft".into(),
            "4.0.1".into(),
            Some(210_000),
            Some(44_100),
        );
        plane.samples.insert_stem(&stem).unwrap();
        stem
    }

    #[test]
    fn sample_add_promotes_stem_with_complete_attribution_and_enqueues_analysis() {
        let plane = in_memory_plane();
        let track = ReferenceTrack::new_upload("trackhash".into(), Some("Trust".into()), Some("Brent Faiyaz".into()), None, None);
        plane.references.insert_track(&track).unwrap();
        let stem = seed_stem(&plane, track.id);

        let args = SampleAddArgs {
            stem: stem.id,
            project: ProjectId::new(),
            artist: "Brent Faiyaz".into(),
            time_range: (12_000, 18_000),
            rights: RightsArg::CopyrightedUncleared,
            title: None, // falls back to the track title "Trust"
        };
        let (frag, attr, job) = do_sample_add(&plane, &args).unwrap();

        // The fragment is sampled + captured, audio = the stem.
        assert_eq!(frag.provenance().as_str(), "sampled");
        assert_eq!(frag.state().as_str(), "captured");
        assert_eq!(frag.audio_uri, stem.audio_uri);
        let stored = plane.repo.get_fragment(frag.id).unwrap().unwrap();
        assert_eq!(stored.id, frag.id);

        // Attribution is complete, persisted, title fell back to the track title.
        assert_eq!(attr.attribution.source_title, "Trust");
        assert_eq!(attr.attribution.source_artist, "Brent Faiyaz");
        let got = plane.samples.get_attribution(frag.id).unwrap().unwrap();
        assert_eq!(got, attr);

        // A FeatureExtract job for the sample (it travels the human analysis path).
        let rec = plane.queue.consume().unwrap().expect("one analysis job");
        assert_eq!(rec.id, job);
        match rec.envelope {
            JobEnvelope::FeatureExtract { fragment_id } => assert_eq!(fragment_id, frag.id),
            other => panic!("expected FeatureExtract, got {other:?}"),
        }
    }

    #[test]
    fn sample_add_rejects_incomplete_attribution_and_creates_nothing() {
        let plane = in_memory_plane();
        // A track with NO title, and no --title flag → source_title is missing.
        let track = ReferenceTrack::new_upload("trackhash".into(), None, None, None, None);
        plane.references.insert_track(&track).unwrap();
        let stem = seed_stem(&plane, track.id);

        let args = SampleAddArgs {
            stem: stem.id,
            project: ProjectId::new(),
            artist: "   ".into(), // whitespace-only artist = missing
            time_range: (12_000, 18_000),
            rights: RightsArg::Unknown,
            title: None, // and no title anywhere
        };
        let err = do_sample_add(&plane, &args).unwrap_err();
        match err {
            // The variant now carries the TYPED `IncompleteAttribution` (its `missing` field list),
            // not a pre-rendered string; its `Display` still joins the same human message the CLI
            // prints, and the typed fields are what the HTTP layer serializes.
            CliError::IncompleteAttribution(ref e) => {
                let msg = e.to_string();
                assert!(msg.contains("source_title"));
                assert!(msg.contains("artist"));
                assert!(e.missing.contains(&nameless_core::attribution::AttributionField::SourceTitle));
                assert!(e.missing.contains(&nameless_core::attribution::AttributionField::SourceArtist));
            }
            other => panic!("expected IncompleteAttribution, got {other:?}"),
        }
        // Nothing was created: no fragment, no attribution, no job.
        assert!(plane.repo.list_fragments(None).unwrap().is_empty());
        assert!(plane.queue.consume().unwrap().is_none());
    }

    /// WR-02: a failure AFTER the fragment+attribution writes (here, the analysis-job enqueue)
    /// compensates by deleting both — the graph is left as if the promotion never happened, so no
    /// orphaned `sampled` fragment and no dangling credit row survive.
    #[test]
    fn sample_add_rolls_back_fragment_and_attribution_when_enqueue_fails() {
        // A 0-capacity queue rejects every enqueue → deterministically forces the post-write failure.
        let plane = Plane {
            store: Box::new(InMemoryObjectStore::new()),
            repo: Box::new(InMemoryFragmentRepo::new()),
            queue: Box::new(InMemoryJobQueue::new(0)),
            references: Box::new(InMemoryReferenceStore::new()),
            samples: Box::new(InMemorySampleStore::new()),
        };
        let track = ReferenceTrack::new_upload(
            "trackhash".into(),
            Some("Trust".into()),
            Some("Brent Faiyaz".into()),
            None,
            None,
        );
        plane.references.insert_track(&track).unwrap();
        let stem = seed_stem(&plane, track.id);

        let args = SampleAddArgs {
            stem: stem.id,
            project: ProjectId::new(),
            artist: "Brent Faiyaz".into(),
            time_range: (12_000, 18_000),
            rights: RightsArg::CopyrightedUncleared,
            title: None,
        };
        // The enqueue fails → the whole promotion is rolled back.
        assert!(matches!(do_sample_add(&plane, &args), Err(CliError::Job(_))));
        // Neither the fragment nor its attribution survives the failure.
        assert!(plane.repo.list_fragments(None).unwrap().is_empty());
        assert!(plane
            .samples
            .list_project_attributions(args.project)
            .unwrap()
            .is_empty());
    }

    /// WR-04: a slice that runs past the stem's known length is rejected (SAMP-05) and creates
    /// nothing — the credits sheet never records a range the source does not contain.
    #[test]
    fn sample_add_rejects_slice_beyond_stem_length() {
        let plane = in_memory_plane();
        let track = ReferenceTrack::new_upload(
            "trackhash".into(),
            Some("Trust".into()),
            Some("Brent Faiyaz".into()),
            None,
            None,
        );
        plane.references.insert_track(&track).unwrap();
        let stem = seed_stem(&plane, track.id); // duration_ms = 210_000

        let args = SampleAddArgs {
            stem: stem.id,
            project: ProjectId::new(),
            artist: "Brent Faiyaz".into(),
            time_range: (200_000, 220_000), // end 220_000 > stem 210_000
            rights: RightsArg::CopyrightedUncleared,
            title: None,
        };
        assert!(matches!(
            do_sample_add(&plane, &args),
            Err(CliError::SampleOutOfRange(_))
        ));
        // Nothing created: no fragment, no attribution, no job.
        assert!(plane.repo.list_fragments(None).unwrap().is_empty());
        assert!(plane
            .samples
            .list_project_attributions(args.project)
            .unwrap()
            .is_empty());
        assert!(plane.queue.consume().unwrap().is_none());
    }

    #[test]
    fn sample_add_unknown_stem_is_not_found() {
        let plane = in_memory_plane();
        let args = SampleAddArgs {
            stem: StemId::new(),
            project: ProjectId::new(),
            artist: "x".into(),
            time_range: (0, 1_000),
            rights: RightsArg::Unknown,
            title: Some("t".into()),
        };
        assert!(matches!(do_sample_add(&plane, &args), Err(CliError::NotFound(_))));
    }

    #[test]
    fn credits_lists_a_projects_samples() {
        let plane = in_memory_plane();
        let project = ProjectId::new();
        let track = ReferenceTrack::new_upload("trackhash".into(), Some("Trust".into()), None, None, None);
        plane.references.insert_track(&track).unwrap();
        let stem = seed_stem(&plane, track.id);
        let args = SampleAddArgs {
            stem: stem.id,
            project,
            artist: "Brent Faiyaz".into(),
            time_range: (12_000, 18_000),
            rights: RightsArg::CopyrightedUncleared,
            title: Some("Trust".into()),
        };
        do_sample_add(&plane, &args).unwrap();

        let rows = plane.samples.list_project_attributions(project).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].attribution.source_artist, "Brent Faiyaz");
        // A different project has no credits.
        assert!(plane
            .samples
            .list_project_attributions(ProjectId::new())
            .unwrap()
            .is_empty());
    }
}
