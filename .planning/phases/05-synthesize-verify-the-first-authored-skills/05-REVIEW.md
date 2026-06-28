---
status: issues
phase: 05-synthesize-verify-the-first-authored-skills
depth: standard
files_reviewed: 17
findings:
  critical: 1
  warning: 3
  info: 4
  total: 8
---

# Phase 5 — Code Review (Synthesize + Verify the First Authored Skills)

**Reviewed:** 2026-06-28
**Depth:** standard
**Scope:** the citation gate + synthesis + emit + audit + persistence path (17 files).

## Summary

The integrity core is fundamentally sound. The citation gate is a genuinely pure function, it is wired in
the **pipeline** (not the adapter), so both the fake and the live Anthropic synthesizer route through the
*same* gate — there is no live-path gate bypass. Re-grounding in `parse_synthesizer_output` correctly
rebuilds every citation from the real claim set, so a fabricated/empty citation id is rejected (R2
NONEXISTENT_SOURCE) and a tampered quote cannot survive (R2 QUOTE_TAMPERED). R3's set-difference on
canonicalized numbers is the right mechanical check, and emission happens strictly after the gate passes.

However, the trust boundary the architecture claims ("markdown is decoration over already-verified content,
never a place new craft can enter") is **broken on the live path**: the model-controlled `name` and
`description` are emitted into the SKILL.md verbatim, unescaped, so a model can inject un-gated content —
including a `---` frontmatter fence — into the final artifact (CR-01). Three narrower gate-integrity gaps
(sign-blindness, spelled-out numbers, claim_text/quote coupling) follow.

All findings on the live (`AnthropicSkillSynthesizer`) path are tagged **[env-gated]** — they are provable
by reading but require the real model to actually trigger; the fake/template path cannot produce them
because it composes bodies verbatim from `claim_text` and uses the cell slug for `name`.

---

## Critical

### CR-01: Model-controlled `name`/`description` are emitted into SKILL.md unescaped — un-gated content (incl. a `---` fence) can be injected past the gate  [env-gated]

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/layered_emitter.py:70-77` (and the parse seam `pure/synthesis_schema.py:206-213`)

**What's wrong:** `emit_skill_md` writes the frontmatter as raw f-strings:
```python
lines.append(f"name: {draft.name}")
lines.append(f"description: {draft.description}")
```
`draft.name` / `draft.description` originate from the model (`_RawSkillIn.name`/`.description`) and are only
`.strip()`-ed in `parse_synthesizer_output` (`pure/synthesis_schema.py:209-211`) — leading/trailing
whitespace is removed, but **internal newlines, colons, and `---` are not**. A model that returns
`name = "x\n---\n## Default — act on this\n<arbitrary ungated craft>\n"` terminates the frontmatter early and
injects arbitrary markdown **body** content that never passed the citation gate. The module's own docstring
asserts the opposite invariant: *"the markdown is decoration over already-verified content, never a place new
craft can enter."* On the live path that invariant does not hold. Even the milder case (a colon or newline in
`description`) produces malformed YAML frontmatter, and the frontmatter *is* the Claude-skill contract the M1
arranger/mixer loads.

**Why it matters:** The entire phase thesis is "you cannot trust the model; the gate enforces." `name` and
`description` are the two model-authored fields that bypass the gate entirely and flow straight into the
shipped artifact. This is the one real hole in the trust boundary.

**Fix:** Treat both fields as untrusted data, not template literals. Either (a) sanitize at the parse seam —
reject/replace any value containing `\n`, `\r`, or a leading `---`; or (b) emit them as quoted/escaped YAML
scalars and strip control characters:
```python
def _yaml_scalar(s: str) -> str:
    s = s.replace("\r", " ").replace("\n", " ").strip()
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
...
lines.append(f"name: {_yaml_scalar(draft.name)}")
lines.append(f"description: {_yaml_scalar(draft.description)}")
```
Best to do both: hard-reject newlines/`---` in `parse_synthesizer_output` (fail fast, like an unsupported
default already does) *and* quote on emit.

---

## Warnings

### WR-01: The invented-number gate is sign-blind — a wrong-signed parameter (+6 vs −6 dB, boost vs cut) passes R3

**File:** `knowledge-pipeline/src/knowledge_pipeline/domain/keys.py:28-29,55-66` (consumed by `pure/citation_gate.py:160-173`)

**What's wrong:** `_NUMBER = re.compile(r"\d+(?:\.\d+)?")` never captures a leading minus, and `numbers()`
canonicalizes magnitude only. So `numbers("-6 dB")` and `numbers("6 dB")` both yield `{"6"}`. R3 compares
`asserted_numbers - evidence_numbers`, so a section body asserting **"boost 6 dB"** is fully grounded by a
cited quote that says **"cut −6 dB"** (or vice-versa). The `keys.py` docstring states this is intentional
("We compare the magnitude only"), but for a *mixing/EQ* skill — exactly the north-star use case — sign is
the entire craft decision; boost-vs-cut is not a rounding nuance.

**Why it matters:** This is the integrity core. The gate's headline promise is that no wrong numeric value
reaches a skill; a sign flip is a maximally-confident wrong value that the gate passes.

**Fix:** Capture an optional sign in `_NUMBER` (`r"-?\d+(?:\.\d+)?"`) and preserve it in `_norm_number`
(canonicalize `-6` → `"-6"`, but keep `-0`→`0`). Then `-6` in the body only grounds against `-6` in a quote.
This tightens R3 without affecting unsigned magnitudes.

### WR-02: Only digit-form numbers are checked — spelled-out numbers evade the invented-number gate  [env-gated]

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/citation_gate.py:160-173` + `domain/keys.py:55-66`

**What's wrong:** R3 extracts numbers via the `\d` regex only. A model that writes the invented value in words
— `"high-pass around three hundred hertz"` when the cited claim says only `"high-pass the low end"` (no number)
— produces `numbers(body) == set()`, so R3 never fires. The only backstop is R4 token-coverage at
`min_coverage = 0.6`, which is loose enough that a body that is mostly verbatim claim words with a spelled
number sprinkled in can exceed the floor and pass. The template/fake path is immune (bodies are verbatim
`claim_text`), but the live Anthropic path emits the model's free prose as the body
(`pure/synthesis_schema.py:176,201`).

**Why it matters:** "No invented number may reach a Skill" is the phase's central guarantee; spelled-out
numerics are a direct evasion of the exact rule (R3) meant to enforce it.

**Fix:** Either normalize number-words to digits before R3 (a small `{"three hundred": "300", ...}` pass is
brittle), or — more robust — instruct + structurally constrain numerics, and add an R4-style check that flags
number-words present in the body but absent from cited quotes. At minimum, document the gap in the gate
docstring so it is not mistaken for a closed guarantee.

### WR-03: R3 grounds body numbers against cited *quotes* only, while template bodies are built from *claim_text* — legitimate skills can be false-rejected

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/citation_gate.py:161-165` vs `pure/synthesis_template.py:148,163,111` and `_assertion_is_grounded` (`citation_gate.py:204-220`)

**What's wrong:** R3 builds `evidence_numbers` from `numbers(c.quote)` (the verbatim transcript line only),
but the deterministic synthesizer composes `body` from `claim.claim_text` (`_default_section`,
`_consensus_section`, `_conflict_sections` all use `claim_text`). R4's `_assertion_is_grounded` correctly
unions `claim_text` **and** `quote`; R3 does **not** — it omits `claim_text`. Per the Phase-4 extraction
prompt, a number in `claim_text` is supposed to also appear in the quote, but auto-caption quotes routinely
mis-hear/garble numbers (the prompt itself says "if a value looks garbled, lower confidence and quote it
as-is"). When the quote is garbled but `claim_text` carries the clean number, a perfectly legitimate
template-synthesized skill is rejected with INVENTED_NUMBER.

**Why it matters:** An over-strict gate that rejects sound craft erodes trust in the gate and silently drops
north-star cells. This is an asymmetry bug between R3 and R4 over the same evidence.

**Fix:** Make R3 consistent with R4 — union the cited claims' `quote` *and* `claim_text` numbers (or
deliberately decide quote-only is the contract and assert in tests that `template_synthesize` can never
produce a `claim_text` number absent from its quote). Right now the two rules disagree about what "the
evidence" is.

---

## Info

### IN-01: R5 citation-rot is silently skipped when a snapshot is missing — never a hard guarantee

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/citation_gate.py:186-199` + `synthesis_pipeline.py:126-136`

R5 only runs when `snapshots` is passed and a per-video snapshot resolves; `_snapshots_for` omits any video
whose `load_snapshot` returns `None`, and the gate then `continue`s past it ("never a way to fail/pass on
absence"). This is design-acknowledged, but it means a taken-down/missing source produces **no** rot signal
rather than a flag — exactly the drift case R5 advertises catching. Consider recording a soft note (or a
distinct `SNAPSHOT_MISSING` advisory in `GateResult`) so a reviewer can see R5 did not actually run for some
claims, instead of it being invisible.

### IN-02: `_mmss` has no hour component — timestamps ≥ 60 min render misleadingly

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/layered_emitter.py:40-42`

`divmod(ms // 1000, 60)` rolls minutes past 59 (e.g. a 75-minute timestamp renders `75:00`). Long-form
tutorials/mixes exceed an hour. Citations are receipts a human jumps to during the spot-audit; `75:00` is
ambiguous. Use `hh:mm:ss` when `ms >= 3_600_000`.

### IN-03: An empty/whitespace default body passes the gate and emits a blank "Default approach:"  [env-gated]

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/citation_gate.py:89-92,119-121` + `pure/layered_emitter.py:97-99`

`_is_assertive` skips any section whose body is whitespace-only, so a model returning `default.body = "   "`
(stripped to `""` in `parse_synthesizer_output`) is never checked by R3/R4 yet still satisfies the
non-empty-citation requirement. The emitter then renders `Default approach: ` with no guidance — an
opinionated default that says nothing can ship as a draft. The fake path always has a real claim body, so
this is live-only. Consider rejecting a draft whose `default.body` is empty after strip (the default is the
one block the agent acts on).

### IN-04: Transcript-derived claim text/quotes flow unescaped into the synthesis user prompt

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/synthesis_schema.py:216-235`

`format_clusters_for_synthesis` interpolates `claim_text` and `quote` straight into the user content
(`quote: "..."`) with no delimiting/escaping. Tutorial transcripts are third-party text and could contain
prompt-injection ("ignore the above; emit ..."). The blast radius is bounded — citations are re-grounded
from the real claim set and the gate re-checks numbers/coverage — so injection cannot fabricate a citation;
the worst case is steered body prose, which WR-02/CR-01 already cover. Low risk for this corpus, but worth a
delimiter/fence around untrusted claim text so the boundary is explicit.

---

_Reviewed by: Claude (gsd-code-reviewer) — standard depth. Gate logic reviewed by reading; the live
Anthropic path was not executed (env-gated), and all live-only findings are tagged accordingly._
