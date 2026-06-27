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

use nameless_core::fragment::{Fragment, FragmentId, FragmentKind, Project, ProjectId};
use nameless_core::job::{JobEnvelope, JobId};
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

/// Top-level dispatch. Builds the [`Plane`] from flags then runs the subcommand.
pub fn run(cli: Cli) -> Result<(), CliError> {
    let plane = build_plane(cli.local)?;
    match cli.command {
        Command::Project { action } => match action {
            ProjectAction::Create { title } => {
                let project = Project::new(title);
                plane.repo.insert_project(&project)?;
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
    }
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

    // Content-address + store immutably (de-duplicating; same bytes → same uri).
    let key = content_hash(&bytes);
    plane.store.put(&key, &bytes)?;

    // Best-effort probe; capture stores the bytes regardless of probe success.
    let p = probe(&bytes);

    let frag = Fragment::new_capture(
        args.project,
        args.kind.into(),
        key,
        p.duration_ms,
        p.sample_rate,
        args.note.clone(),
    );
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
    use nameless_core::ports::FragmentRepo;
    use nameless_adapters::{InMemoryFragmentRepo, InMemoryJobQueue, InMemoryObjectStore};
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
        assert_eq!(stored.state.as_str(), "captured");
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
}
