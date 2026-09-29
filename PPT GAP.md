# PPT vs. README — Gap Analysis
**Source:** `updated_SIH_Team_Athena - proper one.pptx` (6 slides)  
**Reference:** `read-jashan.md` (authoritative technical reference)

---

## Overall verdict

The PPT is **very thin**. It has 6 slides where at least 3–4 more are needed to cover the system properly. Several of the most compelling, differentiating parts of the project are **completely absent**. The slides that do exist are often vague or contain incorrect/outdated claims.

---

## What the PPT covers vs. what's actually in the system

### ✅ Slide 1 — Title / Meta
Fine. PS ID, team, theme are correct.

### 🟡 Slide 2 — Proposed Solution
**Partially correct, but has two problems:**

1. **Duplicate bullet:** "Quantum Circuit Breaker" appears **twice** (lines 19 and 22) with slightly different wording. One should be removed.
2. **Missing from this slide:**
   - The **3-party protocol** (Alice signs; Bob and Charlie verify *independently*) — the core premise is never stated clearly.
   - The **commitment scheme** (hash sent at distribution time that binds message + signature). This is how tampering and replay are caught.
   - That the detector is **blind to attack labels** — it only sees verifier observations, not the injector setting. This is a key correctness claim.
   - **Persistent state (SQLite):** link states, nonces and audit records survive restarts.

### 🔴 Slide 3 — Technical Approach
**Content is completely missing from the extracted text.** Slide 3 appears blank or has only images/diagrams with no text layer. The following are **absent**:

| Missing topic | Where it is in the README |
|:---|:---|
| The 5-step protocol (Prepare → Teleport → Commit → Reveal → Verify) | §5 "How it works" |
| Qiskit Aer circuit with mid-circuit measurement + feed-forward (`X^m2 Z^m1`) | §5.3 |
| Sequential early abort (4 blocks, stop when decisive) | §8, §9 |
| The WATCH→QUARANTINE→PROBATION state machine diagram | §9 |
| Tier 1 (Binomial/QBER alarm) vs. Tier 2 (signer vs. channel attribution) decision tree | §8 |
| Fisher's method for combining p-values from multiple weak alerts | §9 |
| The router (`alice→QR-1→bob/charlie`) and per-hop states | §9 |
| Adaptive test allocation (2× tokens on WATCH/PROBATION) | §9 |

### 🟡 Slide 4 — Feasibility & Viability
**Mostly OK, but has one significant error and several gaps:**

- ❌ **Wrong frontend tech:** Slide says "React.js dashboard" — the actual frontend is **plain HTML/CSS/JavaScript** (no React). This is a factual error that judges can verify.
- ❌ **Missing thresholds detail:** Threshold diagram is vague. The actual values (`e0 = 2%`, `s_a`, `s_v`, Tier 1 α = 0.01, Tier 2 α₂ = 0.05, immediate quarantine p ≤ 0.001) are what make this credible.
- ❌ **Missing: measured experiment results.** The PPT makes zero mention of the seeded experiments (200 trials, 3 signature lengths). The numbers are the strongest evidence that the system works.

### 🟡 Slide 5 — Impact & Benefits
**Claims are OK but one is overstated:**

- 🟡 **"Information-Theoretic Security"** is described as a benefit. Per `read-jashan.md §16`, the system does **NOT** claim end-to-end information-theoretic security — the message commitment and audit signatures are computational (SHA-256, Ed25519). This should be corrected to avoid being challenged by judges.
- ❌ **Missing: Q-Cert / Audit trail as a benefit.** The downloadable, hash-chained, offline-verifiable audit record with optional ML-DSA-65 hybrid post-quantum signing is one of the project's strongest claims for regulated sectors (defense, banking). It is not mentioned here at all.
- ❌ **Missing: "Reject-only" vs. "quarantine" distinction.** Replay/impersonation never lock the link. This is a deliberate, defensible design choice that judges may ask about.

### 🟡 Slide 6 — Research & References
**References are correct. Missing:**

- The **basis-schedule experiment** finding (using a public/predictable basis lets Eve drive forgery contradiction rate from 0.23 → 0.005; HEDWIG uses random bases). This is a novel result that belongs in references or a dedicated findings slide.
- No reference to V2 technical report / STATUS.md (internal documentation).
- Could add: NIST FIPS 204 (ML-DSA-65 standard) as a reference since the system uses it for post-quantum signing.

---

## Completely missing slides

The PPT has **no slide at all** for:

| Missing slide topic | Justification |
|:---|:---|
| **Live Demo / Dashboard walkthrough** | Judges will see the 3-role portal; a labeled screenshot slide helps them orient |
| **Measured results table** | 200-trial seeded experiments; detection rates per attack type per signature length — this is the most persuasive quantitative evidence |
| **Attacks you can simulate** | All 8 injectors (authentic, eve_forgery, eve_intercept, message_tampering, repudiation, replay, impersonation, dishonest_bob) with how each is caught |
| **What we claim vs. what we don't** | Proactively addresses the "information-theoretic security" vs. "computational" distinction, and that bounds are illustrative — avoids being tripped up by a careful judge |
| **Cloud deployment / Architecture** | The system now runs on Render.com; a deployment architecture diagram would be impressive |

---

## Priority fixes (ordered by impact)

1. **🔴 Fix "React.js" → plain HTML/CSS/JS** on Slide 4 (factual error)
2. **🔴 Fix "Information-theoretic security" claim** on Slide 5 — change to "physics-backed" or "no-cloning-theorem-grounded" security
3. **🔴 Remove duplicate QCB bullet** on Slide 2
4. **🔴 Add Slide: Measured Results table** (detection rates from 200-trial experiments)
5. **🔴 Add Slide: All 8 attacks + how detected** (with the "reject-only vs. quarantine" distinction)
6. **🟡 Fill in Slide 3** with the 5-step protocol + the WATCH/QUARANTINE state machine diagram
7. **🟡 Add Slide: Dashboard demo screenshots** (Alice, Bob, Charlie pages)
8. **🟡 Add Q-Cert / Audit trail** to Slide 5 benefits
9. **🟡 Add FIPS 204 / ML-DSA-65 reference** to Slide 6

---

## Summary table

| Slide | Status | Critical fix needed? |
|:---|:---|:---|
| 1 — Title | ✅ Good | No |
| 2 — Proposed Solution | 🟡 Partial | Yes (duplicate bullet, missing blind-detector + commit) |
| 3 — Technical Approach | 🔴 Blank/no text | Yes (entire content missing) |
| 4 — Feasibility | 🟡 Partial | Yes (React.js error, missing experiment numbers) |
| 5 — Impact & Benefits | 🟡 Partial | Yes (overclaimed info-theoretic security, missing Q-Cert) |
| 6 — References | 🟡 Partial | Minor (missing FIPS 204, basis-schedule finding) |
| — | 🔴 Missing | Add: Measured Results slide |
| — | 🔴 Missing | Add: Attack Suite slide |
| — | 🟡 Missing | Add: Dashboard Demo slide |
| — | 🟡 Missing | Add: What we claim / don't claim slide |
