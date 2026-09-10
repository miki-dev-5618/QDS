# Team ATHENA — 5-Minute Pitch Script
**PS 26141 | Quantum-Inspired Cyber Threat Detection for Digital Signature Security**
**Theme:** Blockchain & Cybersecurity | **Category:** Software

Total time: ~5:00. Speaker A and Speaker B alternate. Timings are cumulative — use them to pace, not read aloud.

---

## SPEAKER A — Opening, Problem, Solution (0:00 – 2:20)

**[0:00 – 0:20] Hook + Intro**
> "Good [morning/afternoon] judges. We're Team ATHENA, and we're here to solve a threat that most cybersecurity systems today aren't even designed to see: quantum computers breaking digital signatures. I'm [Name], and with me is [Partner Name]."

**[0:20 – 1:00] The Problem**
> "Every digital signature you trust today — on banking transactions, government IDs, defense communications — relies on RSA and ECC. Both depend on math problems: factoring large numbers and discrete logarithms. Those are hard for classical computers, but Shor's algorithm, running on a future quantum computer, solves them in polynomial time. That means anyone can harvest encrypted data *today* and decrypt it the moment quantum hardware matures — a strategy already known as 'Harvest Now, Decrypt Later.'
>
> On top of that, classical channels have a silent flaw: an eavesdropper can tap a wire, copy data packets, and forward them without leaving any trace. Classical cryptography can't detect that kind of interception — it simply isn't built to."

**[1:00 – 2:20] Our Solution**
> "Our answer is a Quantum Digital Signature system built on three pillars.
>
> First, **Teleportation-Based QDS** — we transmit signature tokens using entangled Bell pairs and Pauli feed-forward gates, so the actual fragile quantum information never travels across an open, interceptable channel.
>
> Second, **Orthogonal State Elimination** — instead of verifiers storing raw secret keys that can be stolen, they record *impossible* quantum states through projective measurement. There's no secret key sitting on a server to leak.
>
> Third, **Keep-or-Forward Symmetrisation** — verifiers randomly swap tokens between each other, which mathematically prevents a signer from later denying they signed something, and stops any single verifier from cheating.
>
> Together, this gives us security rooted in the laws of physics — the No-Cloning Theorem and the Uncertainty Principle — not in how hard a math problem is. And critically: if someone taps the channel mid-transmission, the act of eavesdropping itself disrupts the quantum state and triggers an alarm. Interception isn't just prevented — it's *detected*, instantly.
>
> Now I'll hand over to [Partner Name] to walk you through how we built this and why it's practical to deploy."

---

## SPEAKER B — Technical Approach, Feasibility, Impact, Close (2:20 – 5:00)

**[2:20 – 3:10] Technical Approach**
> "Thanks, [Name]. Let's talk implementation.
>
> On the quantum core, we use Python with Qiskit and the Qiskit Aer simulator to handle state preparation, EPR circuit generation, and realistic noise modeling.
>
> For the statistical layer, we use NumPy and SciPy to compute Chernoff-Hoeffding bounds and QBER — Quantum Bit Error Rate — which is how we distinguish real environmental noise from an actual eavesdropping attack.
>
> And for the network and interface, we've built a 5-daemon TCP socket grid using Python's asyncio, paired with a React.js dashboard that shows real-time attack telemetry — so an operator can literally watch an interception attempt happen live."

**[3:10 – 3:50] Feasibility & Challenges**
> "Here's the important part: this doesn't need a quantum computer to run. Because we simulate everything through Qiskit Aer, it deploys entirely on conventional hardware — no superconducting qubits required. And once a signature is issued, validation is near-instant, using O(1) table lookups against deterministic rules.
>
> We're upfront about the challenges too. Channel decoherence — bit and phase flips from environmental noise — can mimic an eavesdropper, so our QBER thresholds have to be tuned carefully. And long-term quantum memory storage isn't yet feasible at scale, which shapes how we architect the verification window."

**[3:50 – 4:35] Impact & Benefits**
> "Why does this matter? Three sectors, immediately.
>
> Defense: this neutralizes Harvest-Now-Decrypt-Later attacks on classified communications. FinTech: it secures high-value transactions with signatures that can't be repudiated. Government: it gives tamper-proof authentication for national ID and critical document verification.
>
> And unlike AI-driven threat detection, our system is **100% deterministic** — no machine learning, so no false positives, no adversarial evasion, and no black-box decisions to explain to a regulator. It's information-theoretically secure, fully auditable, and runs with zero GPU overhead — a fraction of the compute cost of large-scale ML threat models."

**[4:35 – 5:00] Close**
> "RSA and ECC were built for a pre-quantum world. HEDWIG is built for the world that's coming next — signatures secured not by computational difficulty, but by the laws of physics themselves. We'd love to walk you through a live demo or answer any questions. Thank you."

---

### Delivery Notes
- Practice the handoff line at 2:20 so it feels natural, not scripted.
- If judges cut you off for questions, the highest-value line to have landed by then is: *"security backed by physics, not math difficulty — and eavesdropping is detected, not just prevented."*
- Cut the "Delivery Notes" and citation-style references before reading aloud; they're for rehearsal only.