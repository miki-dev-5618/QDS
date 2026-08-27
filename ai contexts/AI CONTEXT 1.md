QUANTUM DIGITAL SIGNATURE PROJECT — VIBE CODER CONTEXT
==============================================================

PROJECT STATUS
--------------
We are building a student prototype around Quantum Communication, Secure Quantum Communication,
Quantum Digital Signatures (QDS), and threat simulation/detection.

IMPORTANT: The professor has explicitly given the project in stages:

STAGE 1 → Build a Quantum Communication Simulator
STAGE 2 → Build a Secure Quantum Communication Simulator
STAGE 3 → Add a QDS Protocol
STAGE 4 → Insert/simulate threats and build detection logic

CURRENT STAGE
-------------
We are CURRENTLY working on STAGE 1 ONLY.

Do NOT jump straight into QDS implementation.

The immediate goal is to create a clean, modular quantum communication simulator that can later
support a QDS protocol without requiring a complete rewrite.

TECHNOLOGY
----------
Preferred quantum SDK/simulation environment:
- Qiskit
- Qiskit Aer where appropriate

Potential application stack later:
- Python backend
- Flask or FastAPI
- React frontend/dashboard

QISKIT QKD LAB
--------------
We are studying/using Qiskit QKD Lab as a reference/foundation for the communication simulator.

Documentation:
https://qiskit.github.io/ecosystem/pypi/qiskit-qkd-lab/

IMPORTANT DISTINCTION:
Qiskit = quantum-computing SDK/infrastructure.
Qiskit QKD Lab = a QKD/BB84-oriented project built using quantum-computing tools.
QKD ≠ QDS.

Do NOT rename QKD code and call it QDS.

Instead, use QKD Lab to understand/reuse suitable quantum communication architecture and
build our own modular layers on top/around the quantum SDK.

CURRENT UNDERSTANDING OF THE TARGET ARCHITECTURE
-----------------------------------------------
Conceptually:

Application/User
      ↓
Message/Data
      ↓
Quantum State Preparation
      ↓
Quantum Communication Layer
      ↓
Quantum Channel
      ↓
Receiver
      ↓
Measurement
      ↓
Results / Statistics

Later this should evolve into:

Application
      ↓
Protocol Layer
      ↓
Security Layer
      ↓
Communication Layer
      ↓
Quantum Simulation Engine
      ↓
Qiskit/Aer

And eventually:

QDS Protocol
      ↓
Quantum Communication
      ↓
Threat/Attack Simulation
      ↓
Observable Measurements
      ↓
Detection Engine
      ↓
Threat Classification
      ↓
Dashboard

STAGE 1 REQUIREMENTS
--------------------
The first simulator should demonstrate basic quantum communication between parties.

At minimum we want to model:

- Alice / sender
- Bob / receiver
- Quantum state preparation
- Quantum circuit/state transmission
- Quantum channel abstraction
- Bob's measurement
- Measurement results
- Basic statistics/logging

Start simple.

Example conceptual flow:

Alice
  ↓
Prepare |0>, |1>, or another simple state
  ↓
Quantum Channel
  ↓
Bob
  ↓
Measurement
  ↓
Result

Do not overcomplicate the first version with QDS, advanced cryptography, or sophisticated
attack detection.

DESIGN PRINCIPLE
----------------
Build the simulator GENERICALLY enough that a future protocol can plug into it.

Avoid hard-coding BB84/QKD assumptions into the core communication layer unless necessary.

Separate:

1. Quantum engine
   - Qiskit circuits
   - gates
   - measurements
   - simulation

2. Communication layer
   - sender
   - receiver
   - channel
   - transmission

3. Protocol layer
   - protocol-specific rules
   - BB84/QKD if used as a demonstration
   - future QDS protocol

4. Security layer
   - security checks
   - verification
   - authentication/freshness later

5. Attack layer
   - Eve
   - intercept/modify/replay/etc. later

6. Detection layer
   - protocol-aware observables
   - deterministic rules/statistics later

Do not force this exact architecture if analysis of QKD Lab suggests a better one.

QKD LAB: WHAT TO ANALYZE
------------------------
When working with the Qiskit QKD Lab code, understand:

- project/folder structure
- important files
- classes/functions
- Alice implementation
- Bob implementation
- quantum state preparation
- channel implementation
- Eve/intercept-resend implementation
- measurement
- result processing
- QBER/statistics
- Qiskit APIs used
- which parts are Qiskit
- which parts are QKD Lab's own code
- which parts are BB84-specific
- which parts are reusable/generic

Do not assume functionality exists without checking the actual code.

REUSE STRATEGY
--------------
For every useful component, classify it as:

A. Reuse directly
B. Reuse with modification
C. Rewrite
D. Do not use

Also check the project's actual license before copying/modifying code.
Preserve required attribution/license notices where applicable.

QDS DIRECTION
-------------
We eventually need to choose a REAL, PUBLISHED QDS protocol.

Do NOT invent a new QDS protocol.

Current candidates being considered:

1. Wallden–Dunjko–Kent–Andersson (WDKA), 2015
   "Quantum digital signatures with quantum key distribution components"
   - Uses BB84-type states/QKD-like components
   - Strong compatibility with a Qiskit/QKD-style simulator
   - Currently the leading candidate for implementation
   - Still requires careful implementation of the actual QDS protocol
   - Multi-party structure (Alice, Bob, Charlie)

2. Yin–Fu–Chen, 2016
   Practical QDS protocol
   - More practical channel assumptions
   - Interesting research alternative
   - More complex for a first student implementation

3. Dunjko–Wallden–Andersson (DWA), 2014
   QDS without quantum memory
   - Uses coherent states/linear-optics concepts
   - Interesting but harder to model using a basic qubit/Qiskit simulator

4. Gottesman–Chuang, 2001
   Foundational QDS construction
   - Important theoretically
   - Less suitable for our first implementation

CURRENT WORKING PREFERENCE:
WDKA is the current leading candidate, NOT a final decision.

Before implementing QDS, compare actual published protocols and confirm:
- algorithm
- signing
- state preparation
- distribution
- measurement
- verification
- assumptions
- security properties
- attack surface
- measurable observables
- Qiskit simulability
- implementation complexity

THREAT MODEL — FUTURE
---------------------
Eventually we want to simulate attacks such as:

- intercept/measure
- channel manipulation
- modification
- replay
- impersonation
- forgery

Important:
There is NO universal "Eve detected" API.

Correct architecture:

Attack
  ↓
Observable consequence
  ↓
Measurement/protocol data
  ↓
Detection calculation/rule
  ↓
Threat classification

Do NOT invent arbitrary thresholds such as "20% error = Eve."

Do NOT assume every verification failure means an attack.

Verification can fail because of:
- noise
- corruption
- malformed input
- implementation errors
- actual attack

Detection thresholds/metrics must come from the selected protocol/security analysis.

QBER is useful in QKD/BB84 contexts but must NOT automatically be treated as the universal QDS
detection metric.

CURRENT PROJECT PHILOSOPHY
--------------------------
We are NOT trying to build a real quantum computer.

We are building a software prototype/simulator using a quantum SDK.

The goal is:
- technically defensible
- modular
- understandable
- demonstrable
- extensible toward QDS
- suitable for a student project

Do not over-focus on quantum physics/math.

Explain concepts using:
- intuitive explanation
- simple examples
- technical terminology
- code-level implementation

CODING RULES FOR THE VIBE CODER
--------------------------------
When generating code:

1. Keep Stage 1 simple and working.
2. Prefer clean modular files over one giant script.
3. Keep protocol-independent code separate from protocol-specific code.
4. Do not hard-code future QDS logic into Stage 1.
5. Use clear names and comments.
6. Add basic tests for important components.
7. Log useful simulation data so future threat detection can consume it.
8. Do not fabricate Qiskit APIs; verify current APIs when uncertain.
9. Do not silently replace Qiskit with another framework.
10. If an architectural decision affects future QDS compatibility, explain it briefly.

IDEAL STAGE 1 OUTPUT
--------------------
We want to eventually have something like:

quantum_project/
├── quantum/
│   ├── simulator.py
│   ├── states.py
│   └── measurement.py
├── communication/
│   ├── sender.py
│   ├── receiver.py
│   └── channel.py
├── protocols/
│   └── base.py
├── security/
├── attacks/
├── detection/
├── tests/
└── main.py

This is only a starting example. Modify it if a better architecture is justified.

FIRST DEVELOPMENT TARGET
------------------------
Build a minimal working simulation:

Alice
  ↓
prepare quantum state
  ↓
send through simulated channel
  ↓
Bob receives
  ↓
Bob measures
  ↓
record result/statistics

Then extend the channel to support configurable noise/errors.

Only after Stage 1 works should we move toward secure communication.

PROJECT ROADMAP
---------------
Phase 1:
Generic quantum communication simulator

Phase 2:
Secure quantum communication mechanisms

Phase 3:
Select and implement a published QDS protocol

Phase 4:
Add Eve/attack simulation

Phase 5:
Build protocol-aware deterministic threat detection

Phase 6:
Add visualization/dashboard

IMPORTANT TERMINOLOGY
---------------------
Use these distinctions correctly:

Quantum communication = transmission of quantum information.

QKD = Quantum Key Distribution.
Purpose: establish a shared secret key.

QDS = Quantum Digital Signature.
Purpose: provide signing/authentication/integrity/non-repudiation-like properties under the
specific QDS protocol/security model.

Qiskit = SDK/framework for quantum programming and simulation.

Qiskit QKD Lab = QKD-focused software/reference implementation, not a QDS protocol.

FINAL GOAL
----------
Build:

Qiskit/Aer
   ↓
Generic Quantum Communication Simulator
   ↓
Secure Communication
   ↓
Published QDS Protocol
   ↓
Attack Simulation
   ↓
Protocol-aware Threat Detection
   ↓
Dashboard

When helping me code, always remember:
WE ARE CURRENTLY AT STAGE 1.
Do not jump ahead unless I explicitly ask.
