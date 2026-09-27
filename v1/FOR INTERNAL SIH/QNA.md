# Team ATHENA — Anticipated Q&A Prep
**PS 26141 | Quantum-Inspired Cyber Threat Detection for Digital Signature Security**

Judges usually probe four angles: feasibility, novelty, technical depth, and real-world deployment. Below are the most likely questions in each category with ready answers. Assign questions to whichever speaker owns that topic (marked A/B based on the pitch split), but both of you should know every answer.

---

## 1. Feasibility & Practicality

**Q: If you don't have real quantum hardware, how is this a real solution and not just a simulation?**
> "Qiskit Aer is a physics-accurate simulator — it models real qubit behavior, noise, and decoherence, so our results reflect what would happen on actual hardware. The architecture itself is hardware-agnostic: the moment quantum processors or QKD-capable network links become commercially available, we swap the simulator backend for real hardware without redesigning the protocol. We're proving the protocol works today, so it's ready the day the hardware is."

**Q: Quantum memory has very short coherence times. Doesn't that make your system impractical for real-world latency?**
> "That's a real constraint, which is why our protocol doesn't rely on long-term quantum storage. Signature tokens are used and verified within the same session — teleportation happens, verification happens via projective measurement almost immediately, and the state doesn't need to persist. We architect around short coherence windows instead of fighting them."

**Q: What happens if there's genuine network noise, not an eavesdropper? Won't you get false alarms?**
> "This is exactly why we use Chernoff-Hoeffding statistical bounds on the QBER instead of a flat threshold. Environmental noise has a predictable statistical signature; an active eavesdropper's intervention pushes error rates outside that bound with high confidence. It's the same class of statistical test used in real QKD systems like BB84, so it's a proven approach, not something we invented from scratch."

**Q: How do you handle scale — can this work for millions of transactions, like a bank needs?**
> "Verification is O(1) — table lookups against deterministic rules — so it's computationally cheap per transaction. The bottleneck in any QDS system is the entangled pair generation/distribution rate, which is a hardware/infrastructure question, not a protocol limitation. As quantum networking infrastructure (quantum repeaters, satellite QKD links) matures, throughput scales with it."

---

## 2. Novelty & Differentiation

**Q: Quantum Digital Signatures aren't a new idea — Gottesman & Chuang proposed this in 2001. What's actually new here?**
> "Correct, the theoretical foundation is 20+ years old. What we've built is a working, deployable software implementation combining three specific techniques — teleportation-based transmission, orthogonal state elimination, and keep-or-forward symmetrisation — into one simulated system with a real-time monitoring dashboard. Most academic QDS papers stop at the math. We've built the simulation, the statistical detection engine, and the operational interface around it."

**Q: Why quantum-based security instead of post-quantum cryptography (lattice-based algorithms like Kyber/Dilithium), which is already being standardized by NIST?**
> "Post-quantum cryptography is still computational — it assumes certain math problems (like lattice problems) stay hard, but that's an assumption, not a guarantee, and could be broken by future algorithms we don't know about yet. Our approach is information-theoretically secure: it's backed by physical laws — the No-Cloning Theorem and Uncertainty Principle — not by an unproven hardness assumption. The two approaches aren't mutually exclusive either; ATHENA is well-suited for the highest-security tier — defense and critical infrastructure — where PQC's assumption-based guarantees aren't good enough."

**Q: Why did you deliberately avoid using AI/ML for this?**
> "AI-based threat detection introduces heuristics, false positives, adversarial evasion, and black-box decisions that are hard to audit or explain to a regulator. Our system is 100% deterministic — every detection is backed by an exact physical measurement, not a probability score from a model. That also means zero GPU overhead and full explainability, which matters a lot for compliance-heavy sectors like banking and defense."

---

## 3. Technical Depth

**Q: Walk me through what actually happens when an eavesdropper taps the channel.**
> "The signature token is transmitted via quantum teleportation using an entangled Bell pair. If an eavesdropper intercepts and measures the qubit mid-channel, the No-Cloning Theorem means they can't copy it without disturbing its state — collapsing the superposition. That disturbance shows up as an anomalous spike in the QBER on the receiving end, which our statistical engine flags in real time on the dashboard."

**Q: What's 'orthogonal state elimination' in plain terms?**
> "Instead of a verifier storing your actual secret key — which is a juicy target for insider theft — they store a record of quantum states that are provably *inconsistent* with a valid signature. To verify, they check the signature against that 'impossible' list rather than against a secret. That means even a verifier can't forge or leak your key, because they never had it in the first place."

**Q: What's the role of the Pauli feed-forward gates?**
> Instead of keeping your secret key, the verifier stores a list of quantum states that can’t be part of a valid signature. To verify a signature, they compare it with this list. Since the verifier never has your secret key, they can’t steal it, leak it, or use it to create fake signatures.


**Q: How does 'keep-or-forward symmetrisation' actually stop repudiation?**
> "After receiving a token, each verifier randomly chooses to either keep it or forward it to another verifier. Because the signer can't predict or control this random choice, they can't selectively convince one verifier while denying it to another — any attempt to cheat gets exposed through the random cross-checking between verifiers."

---

## 4. Real-World Deployment & Business Case

**Q: Who is your actual target customer/user for this?**
> "Three tiers, in order of urgency: (1) Defense and strategic communications, where 'Harvest Now, Decrypt Later' attacks are already happening against classified data; (2) FinTech and banking, for non-repudiable high-value transaction signing; (3) Government infrastructure, for tamper-proof national ID and document verification."

**Q: What does a rollout actually look like — do organizations need new hardware?**
> "In the current simulated form, none — it runs on standard servers through Qiskit Aer. The full information-theoretic security guarantee is unlocked once organizations have access to quantum network links (QKD infrastructure), which several national telecom and defense networks are already piloting. So we're not waiting on hypothetical hardware — we're aligned with infrastructure that's actively being built today."

**Q: How is this different from what China's quantum satellite (Micius) or existing QKD networks already do?**
> "Micius and most QKD networks solve *key distribution* — getting a shared secret key securely between two parties. We're solving a different problem: *digital signatures* — proving authenticity and non-repudiation, which is what banking, legal, and defense document verification actually needs. QDS and QKD are complementary, not competing."

**Q: What's your biggest unresolved risk?**
> "Honestly, quantum memory lifetime and channel decoherence at scale. Our protocol is designed to minimize dependency on long storage, but as we move from simulation to real quantum links, coherence time will directly cap how large or fast a deployment can be until quantum repeater technology matures further."

---

### Quick-Fire Rules
- If a question is outside your prepared area, don't guess — bridge to your teammate: *"That's more [Partner]'s area — [Partner], want to take that?"*
- If you genuinely don't know: *"That's a great question — we haven't validated that specific case yet, but our architecture is designed to extend to it because [reason]."* Never fabricate a number.
- Anchor every answer back to the core differentiator when possible: **physics-based security, not computational-hardness security.**