//! The compact-by-default output contract (PRD §12–13 token strategy — it starts HERE).
//!
//! Every render path in the CLI funnels through this module, and this module has NO path that can
//! emit raw audio bytes or (future) feature arrays. Audio is referenced only by `audio_uri` — the
//! content-hash key, a short string, never the bytes. `--json` emits the same compact summary as a
//! JSON object; the human form prints IDs + a one-line summary. This single chokepoint is what
//! the information-disclosure test (T-01-03) asserts against.

use nameless_core::attribution::{credits_sheet, SampleAttribution};
use nameless_core::fragment::{Fragment, Project, ProjectId};
use nameless_core::job::JobId;
use nameless_core::reference::{
    ReferenceContextSummary, ReferenceRole, ReferenceTrack, ReferenceTrackId,
};
use nameless_core::stems::Stem;

/// Truncate a note to a compact preview so list output stays one line per fragment.
fn preview(note: &str, max: usize) -> String {
    let trimmed = note.trim().replace(['\n', '\r'], " ");
    if trimmed.chars().count() <= max {
        trimmed
    } else {
        let head: String = trimmed.chars().take(max.saturating_sub(1)).collect();
        format!("{head}…")
    }
}

/// `project create` result — the project UUID and nothing else (compact), or `{"project": "…"}`.
pub fn print_project_created(p: &Project, json: bool) {
    if json {
        println!("{}", serde_json::json!({ "project": p.id.to_string() }));
    } else {
        println!("{}", p.id);
    }
}

/// `capture` result — the fragment id plus the enqueued job id. Never the audio/envelope payload.
pub fn print_capture(frag: &Fragment, job: JobId, json: bool) {
    if json {
        println!(
            "{}",
            serde_json::json!({
                "fragment": frag.id.to_string(),
                "state": frag.state().as_str(),
                "audio_uri": frag.audio_uri,
                "enqueued_job": job.to_string(),
            })
        );
    } else {
        println!("captured {} (enqueued {})", frag.id, job);
    }
}

/// `fragments list` — one compact line per fragment, or a JSON array of compact summaries.
pub fn print_fragment_list(frags: &[Fragment], json: bool) {
    if json {
        let arr: Vec<_> = frags
            .iter()
            .map(|f| {
                serde_json::json!({
                    "id": f.id.to_string(),
                    "state": f.state().as_str(),
                    "kind": f.kind.as_str(),
                    "note": f.note_text,
                })
            })
            .collect();
        println!("{}", serde_json::Value::Array(arr));
    } else {
        for f in frags {
            println!(
                "{}  {:<9}  {:<6}  \"{}\"",
                f.id,
                f.state().as_str(),
                f.kind.as_str(),
                preview(&f.note_text, 60)
            );
        }
    }
}

/// `fragments show` — the compact summary (ids, kind, provenance, state, duration, sr, note,
/// audio_uri). `audio_uri` is the hash key (a reference), never bytes.
pub fn print_fragment_show(f: &Fragment, json: bool) {
    if json {
        println!(
            "{}",
            serde_json::json!({
                "id": f.id.to_string(),
                "project_id": f.project_id.to_string(),
                "kind": f.kind.as_str(),
                "provenance": f.provenance().as_str(),
                "state": f.state().as_str(),
                "duration_ms": f.duration_ms,
                "sample_rate": f.sample_rate,
                "audio_uri": f.audio_uri,
                "note": f.note_text,
                "parent_fragment_id": f.parent_fragment_id.map(|p| p.to_string()),
            })
        );
    } else {
        println!("id           {}", f.id);
        println!("project      {}", f.project_id);
        println!("kind         {}", f.kind.as_str());
        println!("provenance   {}", f.provenance().as_str());
        println!("state        {}", f.state().as_str());
        println!(
            "duration_ms  {}",
            f.duration_ms
                .map(|d| d.to_string())
                .unwrap_or_else(|| "-".into())
        );
        println!(
            "sample_rate  {}",
            f.sample_rate
                .map(|d| d.to_string())
                .unwrap_or_else(|| "-".into())
        );
        println!("audio_uri    {}", f.audio_uri);
        if let Some(parent) = f.parent_fragment_id {
            println!("parent       {parent}");
        }
        println!("note         {}", f.note_text);
    }
}

// =================================================================================================
// Reference-track output (Phase 7). Compact by construction: NEVER the CLAP embedding vector or any
// feature array — only the vibe prose + the scalar sonic targets + the embedding's DIMENSION.
// =================================================================================================

/// `reference upload` result — the reference id plus the enqueued analysis job id.
pub fn print_reference_uploaded(track: &ReferenceTrack, job: JobId, json: bool) {
    if json {
        println!(
            "{}",
            serde_json::json!({
                "reference": track.id.to_string(),
                "audio_uri": track.audio_uri,
                "enqueued_job": job.to_string(),
            })
        );
    } else {
        println!("uploaded reference {} (enqueued {})", track.id, job);
    }
}

/// `reference show` — the compact vibe/target summary. `summary` is `None` when the reference has
/// been uploaded but not analyzed yet. This function has NO path that can print the embedding vector
/// (the summary type does not carry it) — the compact-output contract holds structurally.
pub fn print_reference_show(
    track: &ReferenceTrack,
    summary: Option<&ReferenceContextSummary>,
    json: bool,
) {
    if json {
        let analysis = summary.map(|s| {
            serde_json::json!({
                "genre": s.genre,
                "tempo_bpm_min": s.tempo_bpm_min,
                "tempo_bpm_max": s.tempo_bpm_max,
                "lufs": s.lufs,
                "tonal_balance": s.tonal_balance.bands(),
                "stereo_width": s.stereo_width,
                "vibe": s.vibe_description,
                "embedding_dim": s.embedding_dim,      // a count, NEVER the vector
                "analyzer_version": s.analyzer_version,
            })
        });
        println!(
            "{}",
            serde_json::json!({
                "id": track.id.to_string(),
                "audio_uri": track.audio_uri,
                "title": track.title,
                "artist": track.artist,
                "duration_ms": track.duration_ms,
                "sample_rate": track.sample_rate,
                "analysis": analysis,   // null until analyzed
            })
        );
        return;
    }

    println!("id           {}", track.id);
    println!("audio_uri    {}", track.audio_uri);
    println!(
        "title        {}",
        track.title.as_deref().unwrap_or("-")
    );
    println!(
        "artist       {}",
        track.artist.as_deref().unwrap_or("-")
    );
    match summary {
        None => println!("analysis     (pending — not analyzed yet)"),
        Some(s) => {
            println!(
                "genre        {}",
                s.genre.as_deref().unwrap_or("-")
            );
            println!("tempo        {:.0}–{:.0} BPM", s.tempo_bpm_min, s.tempo_bpm_max);
            println!("lufs         {:.1} LUFS", s.lufs);
            let [low, low_mid, mid, high_mid, high] = s.tonal_balance.bands();
            println!(
                "tonal        low {:.2} | low-mid {:.2} | mid {:.2} | high-mid {:.2} | high {:.2}",
                low, low_mid, mid, high_mid, high
            );
            println!("stereo_width {:.2}", s.stereo_width);
            // The 512-d style vector itself is NEVER printed — only its dimension.
            println!("style_embed  {}-d (vector withheld)", s.embedding_dim);
            println!("vibe         {}", s.vibe_description);
        }
    }
}

/// `reference attach` result — confirm the project↔reference link + role.
pub fn print_reference_attached(
    reference: ReferenceTrackId,
    project: ProjectId,
    role: ReferenceRole,
    json: bool,
) {
    if json {
        println!(
            "{}",
            serde_json::json!({
                "reference": reference.to_string(),
                "project": project.to_string(),
                "role": role.as_str(),
            })
        );
    } else {
        println!(
            "attached reference {} to project {} as {}",
            reference,
            project,
            role.as_str()
        );
    }
}

// =================================================================================================
// Stem library + attributed sampling output (Phase 8). Compact by construction: stem/attribution
// rows print ids + labels + the (short) audio_uri key, never audio bytes. The credits sheet is the
// one intentionally-larger artifact (it is the deliverable), and it ALWAYS leads with the
// attribution-≠-permission notice (SAMP-04).
// =================================================================================================

/// `stems separate` result — confirm the enqueued separation job for a track.
pub fn print_stems_separate(track: ReferenceTrackId, job: JobId, json: bool) {
    if json {
        println!(
            "{}",
            serde_json::json!({
                "reference": track.to_string(),
                "enqueued_job": job.to_string(),
            })
        );
    } else {
        println!("separating reference {track} (enqueued {job})");
    }
}

/// `stems list` — one compact line per stem (id, type, separator, audio_uri), or a JSON array.
pub fn print_stem_list(stems: &[Stem], json: bool) {
    if json {
        let arr: Vec<_> = stems
            .iter()
            .map(|s| {
                serde_json::json!({
                    "id": s.id.to_string(),
                    "stem_type": s.stem_type.as_str(),
                    "separator": format!("{}@{}", s.separator_model, s.separator_version),
                    "audio_uri": s.audio_uri,
                    "duration_ms": s.duration_ms,
                })
            })
            .collect();
        println!("{}", serde_json::Value::Array(arr));
    } else {
        for s in stems {
            println!(
                "{}  {:<7}  {}@{:<7}  {}",
                s.id,
                s.stem_type.as_str(),
                s.separator_model,
                s.separator_version,
                s.audio_uri
            );
        }
    }
}

/// `sample add` result — the new sampled fragment id, its attribution summary, and the analysis job.
pub fn print_sample_added(
    frag: &Fragment,
    attr: &SampleAttribution,
    job: JobId,
    json: bool,
) {
    let a = &attr.attribution;
    if json {
        println!(
            "{}",
            serde_json::json!({
                "fragment": frag.id.to_string(),
                "provenance": frag.provenance().as_str(),
                "state": frag.state().as_str(),
                "source_title": a.source_title,
                "source_artist": a.source_artist,
                "stem_type": a.stem_type.as_str(),
                "start_ms": a.start_ms,
                "end_ms": a.end_ms,
                "rights": a.rights_status.as_str(),
                "enqueued_job": job.to_string(),
            })
        );
    } else {
        println!(
            "sampled {} from \"{}\" — {} ({}–{} ms, rights={}) → fragment {} (enqueued {})",
            a.stem_type.as_str(),
            a.source_title,
            a.source_artist,
            a.start_ms,
            a.end_ms,
            a.rights_status.as_str(),
            frag.id,
            job
        );
    }
}

/// `sample show` — a sampled fragment's full attribution + rights status, with the honest notice
/// that **attribution is not permission** (SAMP-04).
pub fn print_sample_show(attr: &SampleAttribution, json: bool) {
    let a = &attr.attribution;
    if json {
        println!(
            "{}",
            serde_json::json!({
                "fragment": attr.fragment_id.to_string(),
                "project": attr.project_id.to_string(),
                "source_track": a.source_track_id.to_string(),
                "stem": a.stem_id.to_string(),
                "source_title": a.source_title,
                "source_artist": a.source_artist,
                "stem_type": a.stem_type.as_str(),
                "start_ms": a.start_ms,
                "end_ms": a.end_ms,
                "rights": a.rights_status.as_str(),
                "rights_note": a.rights_status.note(),
                "attribution_is_not_permission": true,
            })
        );
    } else {
        println!("fragment     {}", attr.fragment_id);
        println!("project      {}", attr.project_id);
        println!("source       \"{}\" — {}", a.source_title, a.source_artist);
        println!("stem         {} ({})", a.stem_type.as_str(), a.stem_id);
        println!("source_track {}", a.source_track_id);
        println!("range        {}–{} ms ({} ms)", a.start_ms, a.end_ms, a.duration_ms());
        println!("rights       {} — {}", a.rights_status.as_str(), a.rights_status.note());
        println!("note         attribution is NOT permission; clear copyrighted/unknown samples before publishing");
    }
}

/// `credits <project>` — the credits sheet (markdown). `--json` wraps the same markdown as a string
/// alongside the structured rows, so a UI can render either. The markdown ALWAYS leads with the
/// attribution-≠-permission notice (built into [`credits_sheet`]).
pub fn print_credits(project_title: &str, rows: &[SampleAttribution], json: bool) {
    let sheet = credits_sheet(project_title, rows);
    if json {
        let samples: Vec<_> = rows
            .iter()
            .map(|r| {
                let a = &r.attribution;
                serde_json::json!({
                    "fragment": r.fragment_id.to_string(),
                    "source_title": a.source_title,
                    "source_artist": a.source_artist,
                    "stem_type": a.stem_type.as_str(),
                    "start_ms": a.start_ms,
                    "end_ms": a.end_ms,
                    "rights": a.rights_status.as_str(),
                })
            })
            .collect();
        println!(
            "{}",
            serde_json::json!({
                "project": project_title,
                "attribution_is_not_permission": true,
                "samples": samples,
                "markdown": sheet,
            })
        );
    } else {
        print!("{sheet}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preview_truncates_long_notes() {
        let long = "a".repeat(100);
        let p = preview(&long, 60);
        assert!(p.chars().count() <= 60);
        assert!(p.ends_with('…'));
    }

    #[test]
    fn preview_keeps_short_notes_and_flattens_newlines() {
        assert_eq!(preview("chorus hook", 60), "chorus hook");
        assert_eq!(preview("line1\nline2", 60), "line1 line2");
    }
}
