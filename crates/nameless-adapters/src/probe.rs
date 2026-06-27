//! Audio probe — extract `duration_ms` + `sample_rate` from raw bytes using symphonia.
//!
//! symphonia is pure Rust (no ffmpeg/native dependency), which is exactly why it was chosen: it
//! keeps the 4GB box buildable. We only run the *format probe* (read the container header + track
//! params), never a full decode, so memory stays bounded even for a large/hostile file.
//!
//! Probing is best-effort: capture stores the original bytes regardless of probe success, so on
//! unsupported or malformed input we return `None`s rather than failing the capture (DoS/garbage
//! resilience — T-01-02). Accepts the common formats enabled in `Cargo.toml` (wav/mp3/flac/
//! m4a-aac).

use std::io::Cursor;

use symphonia::core::formats::FormatOptions;
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::MetadataOptions;
use symphonia::core::probe::Hint;

/// The fields a probe can recover. Both optional — absence is normal, not an error.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct ProbeResult {
    pub duration_ms: Option<u32>,
    pub sample_rate: Option<u32>,
}

/// Probe `bytes` for duration + sample rate. Never panics; returns empty `ProbeResult` on any
/// unsupported/garbage input.
pub fn probe(bytes: &[u8]) -> ProbeResult {
    // symphonia needs an owned, seekable source. `Cursor<Vec<u8>>` implements `MediaSource`.
    let source = Cursor::new(bytes.to_vec());
    let mss = MediaSourceStream::new(Box::new(source), Default::default());

    let probed = symphonia::default::get_probe().format(
        &Hint::new(),
        mss,
        &FormatOptions::default(),
        &MetadataOptions::default(),
    );

    let format = match probed {
        Ok(p) => p.format,
        Err(_) => return ProbeResult::default(), // unknown/garbage format → store bytes anyway
    };

    // Use the default (primary) track's codec parameters.
    let Some(track) = format.default_track() else {
        return ProbeResult::default();
    };
    let params = &track.codec_params;

    let sample_rate = params.sample_rate;
    let duration_ms = match (params.n_frames, sample_rate) {
        (Some(frames), Some(sr)) if sr > 0 => {
            // ms = frames / sample_rate * 1000, rounded.
            let ms = (frames as f64 / sr as f64 * 1000.0).round();
            if ms.is_finite() && ms >= 0.0 {
                Some(ms as u32)
            } else {
                None
            }
        }
        _ => None,
    };

    ProbeResult {
        duration_ms,
        sample_rate,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Build a minimal valid 16-bit PCM mono WAV in-memory (no committed binary fixture).
    fn build_wav(sample_rate: u32, samples: &[i16]) -> Vec<u8> {
        let bits_per_sample: u16 = 16;
        let channels: u16 = 1;
        let data_len = (samples.len() * 2) as u32;
        let byte_rate = sample_rate * channels as u32 * (bits_per_sample as u32 / 8);
        let block_align = channels * (bits_per_sample / 8);

        let mut w = Vec::new();
        w.extend_from_slice(b"RIFF");
        w.extend_from_slice(&(36 + data_len).to_le_bytes());
        w.extend_from_slice(b"WAVE");
        w.extend_from_slice(b"fmt ");
        w.extend_from_slice(&16u32.to_le_bytes()); // subchunk1 size
        w.extend_from_slice(&1u16.to_le_bytes()); // PCM
        w.extend_from_slice(&channels.to_le_bytes());
        w.extend_from_slice(&sample_rate.to_le_bytes());
        w.extend_from_slice(&byte_rate.to_le_bytes());
        w.extend_from_slice(&block_align.to_le_bytes());
        w.extend_from_slice(&bits_per_sample.to_le_bytes());
        w.extend_from_slice(b"data");
        w.extend_from_slice(&data_len.to_le_bytes());
        for s in samples {
            w.extend_from_slice(&s.to_le_bytes());
        }
        w
    }

    #[test]
    fn probes_sample_rate_on_valid_wav() {
        let wav = build_wav(44_100, &[0, 1, -1, 100, -100, 32_767, -32_768, 0]);
        let r = probe(&wav);
        assert_eq!(r.sample_rate, Some(44_100));
        // Duration may be Some (8 frames @ 44.1k ≈ 0ms rounded) — assert it does not panic and is
        // a sane Option; exact value depends on symphonia's frame count reporting for tiny files.
        if let Some(ms) = r.duration_ms {
            assert!(ms < 1000);
        }
    }

    #[test]
    fn garbage_input_returns_none_without_panicking() {
        let r = probe(b"not audio at all, just text");
        assert_eq!(r, ProbeResult::default());
    }

    #[test]
    fn empty_input_returns_none() {
        let r = probe(&[]);
        assert_eq!(r, ProbeResult::default());
    }
}
