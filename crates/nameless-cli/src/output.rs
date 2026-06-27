//! The compact-by-default output contract (PRD §12–13 token strategy — it starts HERE).
//!
//! Every render path in the CLI funnels through this module, and this module has NO path that can
//! emit raw audio bytes or (future) feature arrays. Audio is referenced only by `audio_uri` — the
//! content-hash key, a short string, never the bytes. `--json` emits the same compact summary as a
//! JSON object; the human form prints IDs + a one-line summary. This single chokepoint is what
//! the information-disclosure test (T-01-03) asserts against.

use nameless_core::fragment::{Fragment, Project};
use nameless_core::job::JobId;

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
                "state": frag.state.as_str(),
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
                    "state": f.state.as_str(),
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
                f.state.as_str(),
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
                "provenance": f.provenance.as_str(),
                "state": f.state.as_str(),
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
        println!("provenance   {}", f.provenance.as_str());
        println!("state        {}", f.state.as_str());
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
