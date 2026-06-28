//! Integration tests for the control-plane HTTP API — driven entirely in-process.
//!
//! Each test builds the real router over an in-memory [`Plane`] and drives it with
//! `tower::ServiceExt::oneshot` — NO socket, NO database, NO worker. That is the whole point of the
//! ports-and-adapters design: the handlers run their real control-flow (the same `do_*` use-cases the
//! CLI runs) with only the heavy leaf swapped for the RAM-safe fakes.
//!
//! `[env-gated]` — written to be correct by review; run later with `cargo test -p nameless-api`.

use std::sync::Arc;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::Router;
use serde_json::{json, Value};
use tower::ServiceExt; // for `oneshot`

use nameless_adapters::{
    content_hash, InMemoryFragmentRepo, InMemoryJobQueue, InMemoryObjectStore,
    InMemoryReferenceStore, InMemorySampleStore,
};
use nameless_api::{build_router, AppState};
use nameless_cli::profile::Plane;
use nameless_core::fragment::{Project, ProjectId};
use nameless_core::ports::{AttributionStore, FragmentRepo, ReferenceStore, StemStore};
use nameless_core::reference::{ReferenceContext, ReferenceTrack, ReferenceTrackId, TonalBalance};
use nameless_core::stems::{Stem, StemId, StemType};

// ---- world ------------------------------------------------------------------------------------

/// A seeded world: a project, an analyzed reference (with its array-free context), and one stem of
/// that reference (the separation worker's write). Returns the shared `Arc<Plane>` so a test can keep
/// a handle and assert post-conditions against the SAME store the router writes to.
struct Seed {
    plane: Arc<Plane>,
    project_id: ProjectId,
    reference_id: ReferenceTrackId,
    stem_id: StemId,
}

fn seeded() -> Seed {
    let store = InMemoryObjectStore::new();
    let repo = InMemoryFragmentRepo::new();
    let queue = InMemoryJobQueue::new(64);
    let references = InMemoryReferenceStore::new();
    let samples = InMemorySampleStore::new();

    // A project.
    let project = Project::new("Late Night Tape".into());
    repo.insert_project(&project).unwrap();

    // A reference + its analyzed context (the analyzer's write, via the in-memory test seam). The
    // 512-d embedding is dropped to a dimension by `set_context` exactly as the real read path does.
    let track = ReferenceTrack::new_upload(
        content_hash(b"finished song bytes"),
        Some("Trust".into()),
        Some("Brent Faiyaz".into()),
        Some(210_000),
        Some(44_100),
    );
    references.insert_track(&track).unwrap();
    references
        .set_context(&ReferenceContext {
            reference_track_id: track.id,
            clap_style_embedding: vec![0.1234_f32; 512],
            genre: Some("amapiano".into()),
            tempo_bpm_min: 110.0,
            tempo_bpm_max: 116.0,
            lufs: -9.0,
            tonal_balance: TonalBalance {
                low: 0.3,
                low_mid: 0.25,
                mid: 0.2,
                high_mid: 0.15,
                high: 0.1,
            },
            stereo_width: 0.42,
            vibe_description: "warm, spacious, late-night".into(),
            analyzer_version: "fake-ref-0".into(),
        })
        .unwrap();

    // A stem of that reference (the Demucs worker's write).
    let stem = Stem::new(
        track.id,
        StemType::Vocals,
        content_hash(b"vocal stem bytes"),
        "htdemucs_ft".into(),
        "4.0.1".into(),
        Some(210_000),
        Some(44_100),
    );
    samples.insert_stem(&stem).unwrap();

    let plane = Plane {
        store: Box::new(store),
        repo: Box::new(repo),
        queue: Box::new(queue),
        references: Box::new(references),
        samples: Box::new(samples),
    };

    Seed {
        plane: Arc::new(plane),
        project_id: project.id,
        reference_id: track.id,
        stem_id: stem.id,
    }
}

fn app(plane: Arc<Plane>) -> Router {
    build_router(AppState::from_arc(plane))
}

// ---- request/response helpers -----------------------------------------------------------------

async fn send(app: &Router, req: Request<Body>) -> (StatusCode, Value) {
    let res = app.clone().oneshot(req).await.unwrap();
    let status = res.status();
    let bytes = axum::body::to_bytes(res.into_body(), usize::MAX).await.unwrap();
    let body = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or(Value::Null)
    };
    (status, body)
}

fn get(uri: &str) -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri(uri)
        .body(Body::empty())
        .unwrap()
}

fn post_json(uri: &str, body: &Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .body(Body::from(serde_json::to_vec(body).unwrap()))
        .unwrap()
}

/// Build a `multipart/form-data` body by hand: any number of text fields + an optional file part.
fn post_multipart(uri: &str, fields: &[(&str, &str)], file: Option<(&str, &[u8])>) -> Request<Body> {
    let boundary = "NAMELESSTESTBOUNDARY";
    let mut body: Vec<u8> = Vec::new();
    for (name, value) in fields {
        body.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
            )
            .as_bytes(),
        );
    }
    if let Some((filename, bytes)) = file {
        body.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
            )
            .as_bytes(),
        );
        body.extend_from_slice(bytes);
        body.extend_from_slice(b"\r\n");
    }
    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());

    Request::builder()
        .method("POST")
        .uri(uri)
        .header(
            "content-type",
            format!("multipart/form-data; boundary={boundary}"),
        )
        .body(Body::from(body))
        .unwrap()
}

// ---- projects ---------------------------------------------------------------------------------

#[tokio::test]
async fn list_projects_returns_seeded_project() {
    let seed = seeded();
    let (status, body) = send(&app(seed.plane.clone()), get("/projects")).await;
    assert_eq!(status, StatusCode::OK);
    let arr = body.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["id"], json!(seed.project_id.0.to_string()));
    assert_eq!(arr[0]["title"], json!("Late Night Tape"));
    assert!(arr[0]["created_at_ms"].is_number());
}

#[tokio::test]
async fn create_project_returns_full_project() {
    let seed = seeded();
    let (status, body) =
        send(&app(seed.plane.clone()), post_json("/projects", &json!({ "title": "New Tape" }))).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["title"], json!("New Tape"));
    assert!(body["id"].is_string());
    // It is now listed.
    let (_, list) = send(&app(seed.plane.clone()), get("/projects")).await;
    assert_eq!(list.as_array().unwrap().len(), 2);
}

#[tokio::test]
async fn create_project_blank_title_is_400() {
    let seed = seeded();
    let (status, body) =
        send(&app(seed.plane.clone()), post_json("/projects", &json!({ "title": "   " }))).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert!(body["message"].is_string());
}

// ---- capture (UI-01) --------------------------------------------------------------------------

#[tokio::test]
async fn capture_then_list_and_show_fragment() {
    let seed = seeded();
    let a = app(seed.plane.clone());
    let uri = format!("/projects/{}/fragments", seed.project_id.0);
    let (status, body) = send(
        &a,
        post_multipart(
            &uri,
            &[("note", "chorus hook, over the 2nd drop"), ("kind", "hook")],
            Some(("hook.wav", b"some audio-ish bytes")),
        ),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["state"], json!("captured"));
    assert!(body["fragment"].is_string());
    assert!(body["enqueued_job"].is_string());
    let fragment_id = body["fragment"].as_str().unwrap().to_string();

    // It appears in the project's fragment list.
    let (status, list) = send(&a, get(&format!("/fragments?project={}", seed.project_id.0))).await;
    assert_eq!(status, StatusCode::OK);
    let arr = list.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["kind"], json!("hook"));

    // And `fragments show` returns the compact detail.
    let (status, detail) = send(&a, get(&format!("/fragments/{fragment_id}"))).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(detail["provenance"], json!("human_recorded"));
    assert_eq!(detail["project_id"], json!(seed.project_id.0.to_string()));
    assert_eq!(detail["note"], json!("chorus hook, over the 2nd drop"));
}

#[tokio::test]
async fn capture_into_unknown_project_is_404() {
    let seed = seeded();
    let uri = format!("/projects/{}/fragments", ProjectId::new().0);
    let (status, _) = send(
        &app(seed.plane.clone()),
        post_multipart(&uri, &[("note", "n"), ("kind", "hook")], Some(("x.wav", b"x"))),
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn get_unknown_fragment_is_404() {
    let seed = seeded();
    let (status, _) = send(
        &app(seed.plane.clone()),
        get(&format!("/fragments/{}", uuid::Uuid::new_v4())),
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

// ---- reference (UI-02) ------------------------------------------------------------------------

#[tokio::test]
async fn list_and_show_reference_is_compact_and_array_free() {
    let seed = seeded();
    let a = app(seed.plane.clone());

    let (status, list) = send(&a, get("/references")).await;
    assert_eq!(status, StatusCode::OK);
    let arr = list.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["analyzed"], json!(true));

    let (status, view) = send(&a, get(&format!("/references/{}", seed.reference_id.0))).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(view["title"], json!("Trust"));
    let analysis = &view["analysis"];
    // The compact-output contract: the embedding DIMENSION is present; the vector is not — and there
    // is no field anywhere that holds a raw embedding/feature array.
    assert_eq!(analysis["embedding_dim"], json!(512));
    assert!(analysis.get("clap_style_embedding").is_none());
    assert!(analysis.get("embedding").is_none());
    assert!(analysis.get("style_embedding").is_none());
    // `tonal_balance` is the only array — 5 coarse band ratios (a mix target), never a melody.
    assert_eq!(analysis["tonal_balance"].as_array().unwrap().len(), 5);
    // The whole serialized body contains no 512-length array (the embedding never leaks).
    assert!(!view.to_string().contains("0.1234"));
}

#[tokio::test]
async fn upload_reference_multipart_returns_ids() {
    let seed = seeded();
    let (status, body) = send(
        &app(seed.plane.clone()),
        post_multipart(
            "/references",
            &[("title", "Wasting Time"), ("artist", "Brent Faiyaz")],
            Some(("ref.wav", b"finished reference bytes")),
        ),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(body["reference"].is_string());
    assert!(body["audio_uri"].is_string());
    assert!(body["enqueued_job"].is_string());
}

#[tokio::test]
async fn get_unknown_reference_is_404() {
    let seed = seeded();
    let (status, _) = send(
        &app(seed.plane.clone()),
        get(&format!("/references/{}", ReferenceTrackId::new().0)),
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn attach_reference_uses_snake_case_body() {
    let seed = seeded();
    let uri = format!("/projects/{}/references", seed.project_id.0);
    let (status, body) = send(
        &app(seed.plane.clone()),
        post_json(
            &uri,
            &json!({ "reference_id": seed.reference_id.0.to_string(), "role": "sonic_target" }),
        ),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["role"], json!("sonic_target"));
    assert_eq!(body["reference"], json!(seed.reference_id.0.to_string()));
    assert_eq!(body["project"], json!(seed.project_id.0.to_string()));
}

// ---- stem library + sampling (UI-03) ----------------------------------------------------------

#[tokio::test]
async fn separate_and_list_stems() {
    let seed = seeded();
    let a = app(seed.plane.clone());
    let (status, body) = send(
        &a,
        post_json(&format!("/tracks/{}/stems/separate", seed.reference_id.0), &json!({})),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["reference"], json!(seed.reference_id.0.to_string()));
    assert!(body["enqueued_job"].is_string());

    let (status, stems) = send(&a, get(&format!("/tracks/{}/stems", seed.reference_id.0))).await;
    assert_eq!(status, StatusCode::OK);
    let arr = stems.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["stem_type"], json!("vocals"));
    assert_eq!(arr[0]["separator"], json!("htdemucs_ft@4.0.1"));
}

#[tokio::test]
async fn list_stems_of_unknown_track_is_404() {
    let seed = seeded();
    let (status, _) = send(
        &app(seed.plane.clone()),
        get(&format!("/tracks/{}/stems", ReferenceTrackId::new().0)),
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn add_sample_with_complete_attribution_then_show() {
    let seed = seeded();
    let a = app(seed.plane.clone());
    let uri = format!("/projects/{}/samples", seed.project_id.0);
    let (status, body) = send(
        &a,
        post_json(
            &uri,
            // No `source_title` → falls back to the source track's title "Trust" (as the CLI does).
            &json!({
                "stem_id": seed.stem_id.0.to_string(),
                "source_artist": "Brent Faiyaz",
                "start_ms": 12_000,
                "end_ms": 18_000,
                "rights": "copyrighted_uncleared"
            }),
        ),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["provenance"], json!("sampled"));
    assert_eq!(body["source_title"], json!("Trust"));
    assert_eq!(body["stem_type"], json!("vocals"));
    let fragment_id = body["fragment"].as_str().unwrap().to_string();

    // `sample show` returns the full attribution + the honest rights note.
    let (status, view) = send(&a, get(&format!("/samples/{fragment_id}"))).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(view["attribution_is_not_permission"], json!(true));
    assert_eq!(view["source_artist"], json!("Brent Faiyaz"));
    assert_eq!(view["rights"], json!("copyrighted_uncleared"));

    // Credits now list the sample.
    let (status, credits) =
        send(&a, get(&format!("/projects/{}/credits", seed.project_id.0))).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(credits["attribution_is_not_permission"], json!(true));
    assert_eq!(credits["samples"].as_array().unwrap().len(), 1);
    assert!(credits["markdown"].as_str().unwrap().contains("Attribution is not permission"));
}

#[tokio::test]
async fn add_sample_incomplete_attribution_is_422_and_creates_nothing() {
    let seed = seeded();
    let uri = format!("/projects/{}/samples", seed.project_id.0);
    // Whitespace-only artist → the gate reports `source_artist` missing.
    let (status, body) = send(
        &app(seed.plane.clone()),
        post_json(
            &uri,
            &json!({
                "stem_id": seed.stem_id.0.to_string(),
                "source_artist": "   ",
                "start_ms": 12_000,
                "end_ms": 18_000,
                "rights": "copyrighted_uncleared"
            }),
        ),
    )
    .await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(body["error"], json!("incomplete_attribution"));
    let missing: Vec<String> = body["missing"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap().to_string())
        .collect();
    // The wire name is `source_artist` (NOT the CLI's "artist").
    assert!(missing.contains(&"source_artist".to_string()));

    // NOTHING was created: no attribution row, no sampled fragment in the project.
    assert!(seed
        .plane
        .samples
        .list_project_attributions(seed.project_id)
        .unwrap()
        .is_empty());
    assert!(seed
        .plane
        .repo
        .list_fragments(Some(seed.project_id))
        .unwrap()
        .is_empty());
}

#[tokio::test]
async fn add_sample_unknown_stem_is_404() {
    let seed = seeded();
    let uri = format!("/projects/{}/samples", seed.project_id.0);
    let (status, _) = send(
        &app(seed.plane.clone()),
        post_json(
            &uri,
            &json!({
                "stem_id": StemId::new().0.to_string(),
                "source_artist": "X",
                "source_title": "Y",
                "start_ms": 0,
                "end_ms": 1_000,
                "rights": "unknown"
            }),
        ),
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn get_unknown_sample_is_404() {
    let seed = seeded();
    let (status, _) = send(
        &app(seed.plane.clone()),
        get(&format!("/samples/{}", uuid::Uuid::new_v4())),
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

// ---- project graph + credits (UI-04) ----------------------------------------------------------

#[tokio::test]
async fn project_graph_is_camel_case_and_lists_nodes() {
    let seed = seeded();
    let a = app(seed.plane.clone());
    // Capture a fragment so the graph has a node.
    let _ = send(
        &a,
        post_multipart(
            &format!("/projects/{}/fragments", seed.project_id.0),
            &[("note", "hook"), ("kind", "hook")],
            Some(("h.wav", b"bytes")),
        ),
    )
    .await;

    let (status, graph) = send(&a, get(&format!("/projects/{}/graph", seed.project_id.0))).await;
    assert_eq!(status, StatusCode::OK);
    // The single camelCase field in the whole contract.
    assert_eq!(graph["projectId"], json!(seed.project_id.0.to_string()));
    assert!(graph.get("project_id").is_none());
    let nodes = graph["nodes"].as_array().unwrap();
    assert_eq!(nodes.len(), 1);
    // key/tempo are null in M0 (no feature-read port yet) — the wire shape is still correct.
    assert_eq!(nodes[0]["key"], Value::Null);
    assert_eq!(nodes[0]["tempo_bpm"], Value::Null);
    assert!(graph["edges"].is_array());
}

#[tokio::test]
async fn graph_and_credits_of_unknown_project_are_404() {
    let seed = seeded();
    let a = app(seed.plane.clone());
    let unknown = ProjectId::new().0;
    let (g, _) = send(&a, get(&format!("/projects/{unknown}/graph"))).await;
    assert_eq!(g, StatusCode::NOT_FOUND);
    let (c, _) = send(&a, get(&format!("/projects/{unknown}/credits"))).await;
    assert_eq!(c, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn empty_project_credits_lead_with_the_permission_notice() {
    let seed = seeded();
    let (status, credits) = send(
        &app(seed.plane.clone()),
        get(&format!("/projects/{}/credits", seed.project_id.0)),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(credits["project"], json!("Late Night Tape"));
    assert_eq!(credits["samples"].as_array().unwrap().len(), 0);
    assert!(credits["markdown"].as_str().unwrap().contains("Attribution is not permission"));
}
