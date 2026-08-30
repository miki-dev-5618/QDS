/**
 * ==========================================================================
 * QUANTUM DIGITAL SIGNATURE & CYBER THREAT DETECTION VISUALIZER ENGINE
 * ==========================================================================
 */

document.addEventListener('DOMContentLoaded', () => {
  // Global Simulation State
  const state = {
    signatureLength: 12,
    baselineNoise: 0.02,
    currentStep: 0,
    maxSteps: 5,
    isStepping: false,
    
    // Quantum Data Pools
    aliceTokens: [], // Array of { bit, basis, symbol }
    aliceSyndromes: [], // Array of { m1, m2 } for Bob & Charlie
    bobHeld: [],
    charlieHeld: [],
    bobPauli: [],
    charliePauli: [],
    bobEliminated: [],
    charlieEliminated: [],

    // Attack Scenario
    activeAttack: 'authentic',
    
    // Chernoff Parameters
    chLength: 128,
    chNoise: 0.02,
    chTargetEps: 1e-6
  };

  const SYMBOLS = {
    '0_0': '|0⟩',
    '1_0': '|1⟩',
    '0_1': '|+⟩',
    '1_1': '|−⟩'
  };

  // DOM Elements
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');

  // Tab 1 Elements
  const telSigLenSlider = document.getElementById('tel-sig-len');
  const telSigLenVal = document.getElementById('tel-sig-len-val');
  const telNoiseSlider = document.getElementById('tel-noise');
  const telNoiseVal = document.getElementById('tel-noise-val');
  const btnRunTel = document.getElementById('btn-run-teleportation');
  const btnStepTel = document.getElementById('btn-step-teleportation');
  const btnResetTel = document.getElementById('btn-reset-teleportation');
  const stepNodes = document.querySelectorAll('.step-node');

  const aliceTokenPool = document.getElementById('alice-token-pool');
  const aliceSyndromePool = document.getElementById('alice-syndrome-pool');
  const bobPauliApplied = document.getElementById('bob-pauli-applied');
  const charliePauliApplied = document.getElementById('charlie-pauli-applied');
  const bobHeldPool = document.getElementById('bob-held-pool');
  const charlieHeldPool = document.getElementById('charlie-held-pool');
  const bobElimPool = document.getElementById('bob-elim-pool');
  const charlieElimPool = document.getElementById('charlie-elim-pool');
  const bobVerdictBadge = document.getElementById('bob-verdict-badge');
  const charlieVerdictBadge = document.getElementById('charlie-verdict-badge');

  const telBobMis = document.getElementById('tel-bob-mis');
  const telCharlieMis = document.getElementById('tel-charlie-mis');
  const telSaVal = document.getElementById('tel-sa-val');
  const telSvVal = document.getElementById('tel-sv-val');
  const telProtocolStatus = document.getElementById('tel-protocol-status');

  // Tab 2 & 3 Elements
  const attackCards = document.querySelectorAll('.attack-card');
  const btnInjectAttack = document.getElementById('btn-inject-attack');
  const currentThreatBadge = document.getElementById('current-threat-badge');
  const attackDiagramCanvas = document.getElementById('attack-diagram-canvas');

  const obsBobRate = document.getElementById('obs-bob-rate');
  const obsCharlieRate = document.getElementById('obs-charlie-rate');
  const obsAsymRate = document.getElementById('obs-asym-rate');
  const obsQberRate = document.getElementById('obs-qber-rate');
  const barBobRate = document.getElementById('bar-bob-rate');
  const barCharlieRate = document.getElementById('bar-charlie-rate');
  const barAsymRate = document.getElementById('bar-asym-rate');
  const barQberRate = document.getElementById('bar-qber-rate');

  const engineVerdictTitle = document.getElementById('engine-verdict-title');
  const engineAlertStamp = document.getElementById('engine-alert-stamp');
  const engineVerdictDetails = document.getElementById('engine-verdict-details');
  const engineClassification = document.getElementById('engine-classification');
  const engineConfidence = document.getElementById('engine-confidence');
  const engineIsThreat = document.getElementById('engine-is-threat');
  const diagnosticVerdictCard = document.querySelector('.diagnostic-verdict-card');

  // Tab 4 Elements (Chernoff)
  const chLengthSlider = document.getElementById('ch-length');
  const chLengthVal = document.getElementById('ch-length-val');
  const chNoiseSlider = document.getElementById('ch-noise');
  const chNoiseVal = document.getElementById('ch-noise-val');
  const chTargetEpsSelect = document.getElementById('ch-target-eps');
  const chCalcSa = document.getElementById('ch-calc-sa');
  const chCalcSv = document.getElementById('ch-calc-sv');
  const chCalcDelta = document.getElementById('ch-calc-delta');
  const chCalcLmin = document.getElementById('ch-calc-lmin');
  const footPforge = document.getElementById('foot-pforge');
  const footPfrr = document.getElementById('foot-pfrr');
  const footPrep = document.getElementById('foot-prep');
  const footSecbits = document.getElementById('foot-secbits');
  const chernoffCanvas = document.getElementById('chernoffCanvas');

  // Modal
  const certModal = document.getElementById('cert-modal');
  const btnExportCert = document.getElementById('btn-export-cert');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const btnDismissCert = document.getElementById('btn-dismiss-cert');
  const btnCopyCert = document.getElementById('btn-copy-cert');
  const modalCertContent = document.getElementById('modal-cert-content');

  // =========================================================================
  // 1. NAVIGATION & TAB SWITCHING
  // =========================================================================
  function triggerMathRender() {
    if (typeof renderMathInElement === 'function') {
      try {
        renderMathInElement(document.body, {
          delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '$', right: '$', display: false }
          ],
          throwOnError: false
        });
      } catch (err) {
        console.warn("KaTeX render notice:", err);
      }
    }
  }

  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      tabButtons.forEach(btn => btn.classList.remove('active'));
      tabPanes.forEach(pane => pane.classList.remove('active'));

      button.classList.add('active');
      const targetTab = document.getElementById(button.dataset.tab);
      if (targetTab) {
        targetTab.classList.add('active');
      }

      if (button.dataset.tab === 'tab-chernoff') {
        renderChernoffChart();
      }
      
      setTimeout(triggerMathRender, 50);
    });
  });


  // =========================================================================
  // 2. MATHEMATICAL CHERNOFF-HOEFFDING BOUNDS
  // =========================================================================
  function calculateSecurityBounds(L, e0, pForgMin = 0.25) {
    const maxDelta = (pForgMin - e0) / 3.0;
    const delta = Math.max(0.01, maxDelta);
    const sa = e0 + delta;
    const sv = pForgMin - delta;

    const pForge = Math.min(1.0, Math.exp(-2.0 * (delta ** 2) * L));
    const pFRR = Math.min(1.0, Math.exp(-2.0 * (delta ** 2) * L));
    const gap = sv - sa;
    const pRep = Math.min(1.0, 2.0 * Math.exp(-0.5 * (gap ** 2) * L));
    const secBits = pForge > 0 ? -Math.log2(pForge) : 256.0;

    return { sa, sv, delta, pForge, pFRR, pRep, secBits: Math.min(secBits, 256) };
  }

  function updateChernoffUI() {
    const L = parseInt(state.chLength, 10);
    const e0 = parseFloat(state.chNoise);
    const targetEps = parseFloat(state.chTargetEps);

    const bounds = calculateSecurityBounds(L, e0);
    const lMin = Math.ceil(Math.log(1.0 / targetEps) / (2.0 * (bounds.delta ** 2)));

    chCalcSa.textContent = `${(bounds.sa * 100).toFixed(2)}%`;
    chCalcSv.textContent = `${(bounds.sv * 100).toFixed(2)}%`;
    chCalcDelta.textContent = bounds.delta.toFixed(4);
    chCalcLmin.textContent = `${lMin.toLocaleString()} qubits`;

    footPforge.textContent = bounds.pForge < 1e-4 ? bounds.pForge.toExponential(2) : bounds.pForge.toFixed(4);
    footPfrr.textContent = bounds.pFRR < 1e-4 ? bounds.pFRR.toExponential(2) : bounds.pFRR.toFixed(4);
    footPrep.textContent = bounds.pRep < 1e-4 ? bounds.pRep.toExponential(2) : bounds.pRep.toFixed(4);
    footSecbits.textContent = `${bounds.secBits.toFixed(1)} bits`;

    // Also update Tab 1 telemetry thresholds
    telSaVal.textContent = `${(bounds.sa * 100).toFixed(2)}%`;
    telSvVal.textContent = `${(bounds.sv * 100).toFixed(2)}%`;

    renderChernoffChart();
  }

  function renderChernoffChart() {
    if (!chernoffCanvas || !chernoffCanvas.getContext) return;
    const ctx = chernoffCanvas.getContext('2d');
    const width = chernoffCanvas.width;
    const height = chernoffCanvas.height;

    ctx.clearRect(0, 0, width, height);

    // Padding
    const padX = 60;
    const padY = 40;
    const chartW = width - padX - 30;
    const chartH = height - padY - 30;

    // Draw Grid
    ctx.strokeStyle = 'rgba(70, 100, 150, 0.2)';
    ctx.lineWidth = 1;

    for (let i = 0; i <= 5; i++) {
      const y = padY + (chartH / 5) * i;
      ctx.beginPath();
      ctx.moveTo(padX, y);
      ctx.lineTo(padX + chartW, y);
      ctx.stroke();

      const probLabel = (1.0 - (i / 5.0)).toFixed(1);
      ctx.fillStyle = '#889bb8';
      ctx.font = '11px Space Grotesk';
      ctx.fillText(probLabel, 20, y + 4);
    }

    // Draw Labels
    ctx.fillStyle = '#546682';
    ctx.fillText('Signature Length (L qubits)', padX + chartW / 2 - 60, height - 8);

    const delta = (0.25 - state.chNoise) / 3.0;

    // Function to draw curve
    function drawCurve(calcFn, strokeColor, shadowColor) {
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 2.5;
      ctx.shadowColor = shadowColor;
      ctx.shadowBlur = 8;
      ctx.beginPath();

      for (let x = 0; x <= chartW; x += 4) {
        const lVal = 16 + (x / chartW) * (512 - 16);
        const pVal = calcFn(lVal);
        const yCoord = padY + chartH * (1.0 - pVal);

        if (x === 0) ctx.moveTo(padX + x, yCoord);
        else ctx.lineTo(padX + x, yCoord);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    // Draw Forgery Bound (Cyan)
    drawCurve((l) => Math.min(1.0, Math.exp(-2.0 * (delta ** 2) * l)), '#00f0ff', 'rgba(0, 240, 255, 0.4)');

    // Draw Repudiation Bound (Purple)
    const gap = (0.25 - delta) - (state.chNoise + delta);
    drawCurve((l) => Math.min(1.0, 2.0 * Math.exp(-0.5 * (gap ** 2) * l)), '#a855f7', 'rgba(168, 85, 247, 0.4)');

    // Highlight Current Length Marker
    const currentX = padX + ((state.chLength - 16) / (512 - 16)) * chartW;
    ctx.strokeStyle = '#f59e0b';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(currentX, padY);
    ctx.lineTo(currentX, padY + chartH);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = '#f59e0b';
    ctx.beginPath();
    ctx.arc(currentX, padY + chartH * (1.0 - Math.min(1.0, Math.exp(-2.0 * (delta ** 2) * state.chLength))), 6, 0, Math.PI * 2);
    ctx.fill();
  }

  // =========================================================================
  // 3. TELEPORTATION PROTOCOL SIMULATION LOGIC
  // =========================================================================
  function generateRandomTeleportationState() {
    const N = state.signatureLength;
    state.aliceTokens = [];
    state.aliceSyndromes = [];
    state.bobHeld = [];
    state.charlieHeld = [];
    state.bobPauli = [];
    state.charliePauli = [];
    state.bobEliminated = [];
    state.charlieEliminated = [];

    for (let i = 0; i < N; i++) {
      const bit = Math.random() > 0.5 ? 1 : 0;
      const basis = Math.random() > 0.5 ? 1 : 0;
      const key = `${bit}_${basis}`;
      state.aliceTokens.push({ bit, basis, symbol: SYMBOLS[key] });

      // Alice Bell State Measurement (BSM) outcomes
      const m1_b = Math.random() > 0.5 ? 1 : 0;
      const m2_b = Math.random() > 0.5 ? 1 : 0;
      const m1_c = Math.random() > 0.5 ? 1 : 0;
      const m2_c = Math.random() > 0.5 ? 1 : 0;
      state.aliceSyndromes.push({ bob: { m1: m1_b, m2: m2_b }, charlie: { m1: m1_c, m2: m2_c } });

      // Pauli feed-forward rule
      function getPauliOp(m1, m2) {
        if (m1 === 0 && m2 === 0) return 'I';
        if (m1 === 0 && m2 === 1) return 'X';
        if (m1 === 1 && m2 === 0) return 'Z';
        return 'XZ (-iY)';
      }
      state.bobPauli.push(getPauliOp(m1_b, m2_b));
      state.charliePauli.push(getPauliOp(m1_c, m2_c));

      // Symmetrisation Keep/Forward
      const bobAction = Math.random() > 0.5 ? 'K' : 'F';
      const charlieAction = Math.random() > 0.5 ? 'K' : 'F';

      const bHeld = [];
      const cHeld = [];
      if (bobAction === 'K') bHeld.push('Bob Orig'); else cHeld.push('Bob Fwd');
      if (charlieAction === 'K') cHeld.push('Charlie Orig'); else bHeld.push('Charlie Fwd');

      state.bobHeld.push(bHeld);
      state.charlieHeld.push(cHeld);

      // State Elimination Rule
      function eliminate(bCount, srcBit, srcBasis) {
        const elims = [];
        if (bCount >= 1) {
          const measBasis = Math.random() > 0.5 ? 1 : 0;
          if (measBasis === 0) {
            elims.push(srcBit === 0 ? '|1⟩' : '|0⟩');
          } else {
            elims.push(srcBit === 0 ? '|−⟩' : '|+⟩');
          }
        }
        return elims;
      }

      state.bobEliminated.push(eliminate(bHeld.length, bit, basis));
      state.charlieEliminated.push(eliminate(cHeld.length, bit, basis));
    }
  }

  function updateTeleportationUI() {
    // 1. Render Alice Tokens
    aliceTokenPool.innerHTML = '';
    state.aliceTokens.forEach((t, i) => {
      const chip = document.createElement('span');
      chip.className = 'token-chip';
      chip.textContent = `#${i+1}: ${t.symbol}`;
      aliceTokenPool.appendChild(chip);
    });

    // 2. Render Syndromes
    aliceSyndromePool.innerHTML = '';
    state.aliceSyndromes.forEach((syn, i) => {
      const chip = document.createElement('span');
      chip.className = 'token-chip chip-pauli';
      chip.textContent = `#${i+1} (${syn.bob.m1},${syn.bob.m2})`;
      aliceSyndromePool.appendChild(chip);
    });

    // 3. Render Bob & Charlie Pauli Corrections
    bobPauliApplied.innerHTML = '';
    state.bobPauli.forEach((p, i) => {
      const chip = document.createElement('span');
      chip.className = 'token-chip chip-pauli';
      chip.textContent = `#${i+1}: ${p}`;
      bobPauliApplied.appendChild(chip);
    });

    charliePauliApplied.innerHTML = '';
    state.charliePauli.forEach((p, i) => {
      const chip = document.createElement('span');
      chip.className = 'token-chip chip-pauli';
      chip.textContent = `#${i+1}: ${p}`;
      charliePauliApplied.appendChild(chip);
    });

    // 4. Render Held Registries
    bobHeldPool.innerHTML = '';
    state.bobHeld.forEach((h, i) => {
      const chip = document.createElement('span');
      chip.className = 'token-chip';
      chip.textContent = `#${i+1}: ${h.length} qubit(s)`;
      bobHeldPool.appendChild(chip);
    });

    charlieHeldPool.innerHTML = '';
    state.charlieHeld.forEach((h, i) => {
      const chip = document.createElement('span');
      chip.className = 'token-chip';
      chip.textContent = `#${i+1}: ${h.length} qubit(s)`;
      charlieHeldPool.appendChild(chip);
    });

    // 5. Render Eliminated States
    bobElimPool.innerHTML = '';
    state.bobEliminated.forEach((el, i) => {
      const chip = document.createElement('span');
      chip.className = 'token-chip chip-elim';
      chip.textContent = `#${i+1}: ∉ {${el.join(', ') || 'none'}}`;
      bobElimPool.appendChild(chip);
    });

    charlieElimPool.innerHTML = '';
    state.charlieEliminated.forEach((el, i) => {
      const chip = document.createElement('span');
      chip.className = 'token-chip chip-elim';
      chip.textContent = `#${i+1}: ∉ {${el.join(', ') || 'none'}}`;
      charlieElimPool.appendChild(chip);
    });

    // 6. Verification
    let bobMis = 0;
    let charlieMis = 0;
    let bobTotal = 0;
    let charlieTotal = 0;

    for (let i = 0; i < state.signatureLength; i++) {
      if (state.bobHeld[i].length > 0) {
        bobTotal++;
        if (state.bobEliminated[i].includes(state.aliceTokens[i].symbol)) {
          bobMis++;
        }
      }
      if (state.charlieHeld[i].length > 0) {
        charlieTotal++;
        if (state.charlieEliminated[i].includes(state.aliceTokens[i].symbol)) {
          charlieMis++;
        }
      }
    }

    const bRate = bobTotal > 0 ? (bobMis / bobTotal) * 100 : 0;
    const cRate = charlieTotal > 0 ? (charlieMis / charlieTotal) * 100 : 0;

    telBobMis.textContent = `${bobMis} / ${bobTotal} (${bRate.toFixed(1)}%)`;
    telCharlieMis.textContent = `${charlieMis} / ${charlieTotal} (${cRate.toFixed(1)}%)`;

    bobVerdictBadge.className = bobMis === 0 ? 'verdict-badge pass' : 'verdict-badge fail';
    bobVerdictBadge.textContent = bobMis === 0 ? 'PASS: Authentic Signature (0 Errors)' : `REJECT: ${bobMis} Mismatches`;

    charlieVerdictBadge.className = charlieMis === 0 ? 'verdict-badge pass' : 'verdict-badge fail';
    charlieVerdictBadge.textContent = charlieMis === 0 ? 'PASS: Authentic Signature (0 Errors)' : `REJECT: ${charlieMis} Mismatches`;

    telProtocolStatus.textContent = (bobMis === 0 && charlieMis === 0) ? 'AUTHENTIC ACCEPTANCE' : 'CONTRADICTION DETECTED';
    telProtocolStatus.className = (bobMis === 0 && charlieMis === 0) ? 'tel-val text-green' : 'tel-val text-red';
  }

  function setStepperStep(step) {
    stepNodes.forEach(node => {
      const nodeStep = parseInt(node.dataset.step, 10);
      if (nodeStep <= step) node.classList.add('active');
      else node.classList.remove('active');
    });
  }

  // =========================================================================
  // 4. ATTACK LAB & THREAT ENGINE SIMULATION
  // =========================================================================
  attackCards.forEach(card => {
    card.addEventListener('click', () => {
      attackCards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      const radio = card.querySelector('input[type="radio"]');
      if (radio) {
        radio.checked = true;
        state.activeAttack = radio.value;
      }
    });
  });

  function executeThreatSimulation() {
    const attack = state.activeAttack;
    let bobRate = 0;
    let charlieRate = 0;
    let qber = 0;
    let verdictTitle = '';
    let classification = '';
    let details = '';
    let isThreat = false;
    let stamp = 'AUTHENTIC';
    let stampClass = 'safe';
    let activeRowId = 'row-auth';
    let diagramHtml = '';

    switch (attack) {
      case 'authentic':
        bobRate = 0.0;
        charlieRate = 0.0;
        qber = 0.015;
        verdictTitle = 'PASS: Valid Authentic Quantum Signature';
        classification = 'BENIGN_AUTHENTIC';
        details = 'Zero orthogonal state elimination contradictions detected across all verifiers. All quantum states match announced Pauli eigenstates.';
        isThreat = false;
        stamp = 'AUTHENTIC';
        stampClass = 'safe';
        activeRowId = 'row-auth';
        diagramHtml = `
          <div class="dia-step text-cyan">🟢 Alice prepares Pauli eigenstates {|0⟩, |1⟩, |+⟩, |−⟩}</div>
          <div class="dia-step text-purple">⚡ Teleported via EPR Bell pairs with 100% Pauli fidelity</div>
          <div class="dia-step text-emerald">✅ Bob & Charlie achieve 0 contradictions. Signature Accepted.</div>
        `;
        break;

      case 'external_forgery':
        bobRate = 48.5;
        charlieRate = 51.2;
        qber = 0.02;
        verdictTitle = 'ALERT: Counterfeit / Forged Signature Attack Detected';
        classification = 'EXTERNAL_FORGERY';
        details = 'Both verifiers detected significant orthogonal state contradictions (~50%). Signature was forged blindly without knowledge of private quantum states.';
        isThreat = true;
        stamp = 'FORGERY ALERT';
        stampClass = 'danger';
        activeRowId = 'row-ext';
        diagramHtml = `
          <div class="dia-step text-red">🦹 Eve generates random bit/basis guesses without private quantum states</div>
          <div class="dia-step text-amber">⚠️ Verification against Bob & Charlie eliminated state records</div>
          <div class="dia-step text-red">❌ Error rate ~50% exceeds Chernoff threshold sv (17.3%). Attack blocked.</div>
        `;
        break;

      case 'dishonest_verifier':
        bobRate = 0.0;
        charlieRate = 25.8;
        qber = 0.02;
        verdictTitle = 'ALERT: Dishonest Verifier Forgery Attempt Detected';
        classification = 'DISHONEST_VERIFIER_FORGERY';
        details = 'Recipient detected signature contradictions (~25%) resulting from an inside participant (Bob) attempting to forge Alice\'s signature using partial quantum elimination knowledge.';
        isThreat = true;
        stamp = 'INSIDER THREAT';
        stampClass = 'danger';
        activeRowId = 'row-dishonest';
        diagramHtml = `
          <div class="dia-step text-amber">👤 Dishonest Bob filters candidate states using his own eliminated records</div>
          <div class="dia-step text-amber">📤 Bob sends targeted counterfeit signature to frame Alice to Charlie</div>
          <div class="dia-step text-red">❌ Charlie detects ~25% contradictions on Bob-forwarded tokens. Attack detected!</div>
        `;
        break;

      case 'mitm_intercept':
        bobRate = 26.4;
        charlieRate = 24.1;
        qber = 0.25;
        verdictTitle = 'ALERT: Quantum Channel Interception / Eavesdropping Detected';
        classification = 'EAVESDROPPING_TAMPERING';
        details = 'Eve active Man-in-the-Middle eavesdropped on qubits in transit. QBER (25.0%) exceeds information-theoretic security bound (11.0%).';
        isThreat = true;
        stamp = 'MITM TAMPERING';
        stampClass = 'danger';
        activeRowId = 'row-mitm';
        diagramHtml = `
          <div class="dia-step text-red">⚡ Eve intercepts quantum fiber channel and measures flying qubits</div>
          <div class="dia-step text-purple">💥 Superposition states collapse, causing random state projections</div>
          <div class="dia-step text-red">🚨 Channel QBER spikes to 25.0% > 11.0% limit. Channel aborted.</div>
        `;
        break;

      case 'repudiation':
        bobRate = 0.0;
        charlieRate = 42.0;
        qber = 0.02;
        verdictTitle = 'ALERT: Dishonest Signer Repudiation Attempt Detected';
        classification = 'REPUDIATION_ATTEMPT';
        details = 'Significant asymmetry between verifiers (Bob error: 0.0%, Charlie error: 42.0%). Signer Alice distributed discordant quantum states to deny signing.';
        isThreat = true;
        stamp = 'REPUDIATION';
        stampClass = 'danger';
        activeRowId = 'row-rep';
        diagramHtml = `
          <div class="dia-step text-purple">👩‍💼 Alice generates asymmetric states (correct for Bob, flipped for Charlie)</div>
          <div class="dia-step text-cyan">🔄 Symmetrisation swap distributes Alice\'s discordant states across both parties</div>
          <div class="dia-step text-red">❌ Divergence |e_B - e_C| = 42.0% > 30% threshold. Repudiation attempt identified!</div>
        `;
        break;

      case 'replay_attack':
        bobRate = 0.0;
        charlieRate = 0.0;
        qber = 0.02;
        verdictTitle = 'ALERT: Replay & Stale Token Attack Detected';
        classification = 'REPLAY_ATTACK';
        details = 'Signature tokens possess valid quantum values but contain an expired session nonce or duplicate sequence timestamp.';
        isThreat = true;
        stamp = 'REPLAY DETECTED';
        stampClass = 'danger';
        activeRowId = 'row-ext';
        diagramHtml = `
          <div class="dia-step text-amber">📼 Adversary captures previously valid signature and replays it for new message</div>
          <div class="dia-step text-cyan">🔍 Verifiers check session nonce and sequence timestamp freshness registry</div>
          <div class="dia-step text-red">❌ Stale session identifier detected. Replay transaction rejected!</div>
        `;
        break;

      case 'channel_noise':
        bobRate = 3.2;
        charlieRate = 2.8;
        qber = 0.03;
        verdictTitle = 'NOTICE: Benign Low-Level Channel Noise';
        classification = 'CHANNEL_NOISE';
        details = 'Contradictions remain below acceptable statistical noise threshold (sa = 9.67%). System maintains normal operational integrity.';
        isThreat = false;
        stamp = 'BENIGN NOISE';
        stampClass = 'safe';
        activeRowId = 'row-noise';
        diagramHtml = `
          <div class="dia-step text-blue">🌫️ Fiber thermal fluctuations introduce minor bit-flip perturbations (~3%)</div>
          <div class="dia-step text-cyan">📊 Chernoff statistical filter verifies error remains below acceptance threshold sa</div>
          <div class="dia-step text-green">✅ Benign noise classified. No alarm triggered.</div>
        `;
        break;
    }

    // Update Observables Strip
    obsBobRate.textContent = `${bobRate.toFixed(1)}%`;
    obsCharlieRate.textContent = `${charlieRate.toFixed(1)}%`;
    const asym = Math.abs(bobRate - charlieRate);
    obsAsymRate.textContent = `${asym.toFixed(1)}%`;
    obsQberRate.textContent = `${(qber * 100).toFixed(1)}%`;

    barBobRate.style.width = `${Math.min(100, bobRate * 2)}%`;
    barCharlieRate.style.width = `${Math.min(100, charlieRate * 2)}%`;
    barAsymRate.style.width = `${Math.min(100, asym * 2)}%`;
    barQberRate.style.width = `${Math.min(100, qber * 300)}%`;

    currentThreatBadge.textContent = attack.replace('_', ' ');
    attackDiagramCanvas.innerHTML = diagramHtml;

    // Update Tab 3 Engine Cards
    engineVerdictTitle.textContent = verdictTitle;
    engineVerdictDetails.textContent = details;
    engineClassification.textContent = classification;
    engineConfidence.textContent = isThreat ? '96.5%' : '100.0%';
    engineIsThreat.textContent = isThreat ? 'YES (ACTIVE ALERT)' : 'NO (SECURE)';
    engineIsThreat.className = isThreat ? 'metric-value text-red' : 'metric-value text-green';

    engineAlertStamp.textContent = stamp;
    engineAlertStamp.className = `alert-stamp ${stampClass}`;

    if (isThreat) {
      diagnosticVerdictCard.classList.add('threat-active');
    } else {
      diagnosticVerdictCard.classList.remove('threat-active');
    }

    // Update Active Row in Decision Matrix
    document.querySelectorAll('.decision-matrix-table tr').forEach(r => r.classList.remove('active-rule'));
    const targetRow = document.getElementById(activeRowId);
    if (targetRow) targetRow.classList.add('active-rule');
  }

  // =========================================================================
  // 5. EVENT LISTENERS & INITIALIZATION
  // =========================================================================
  telSigLenSlider.addEventListener('input', (e) => {
    state.signatureLength = parseInt(e.target.value, 10);
    telSigLenVal.textContent = state.signatureLength;
  });

  telNoiseSlider.addEventListener('input', (e) => {
    state.baselineNoise = parseFloat(e.target.value) / 100.0;
    telNoiseVal.textContent = `${parseFloat(e.target.value).toFixed(1)}%`;
  });

  btnRunTel.addEventListener('click', () => {
    generateRandomTeleportationState();
    updateTeleportationUI();
    setStepperStep(5);
  });

  btnStepTel.addEventListener('click', () => {
    if (state.currentStep >= state.maxSteps) state.currentStep = 0;
    state.currentStep++;
    setStepperStep(state.currentStep);
    if (state.currentStep === 1) {
      generateRandomTeleportationState();
    }
    updateTeleportationUI();
  });

  btnResetTel.addEventListener('click', () => {
    state.currentStep = 0;
    setStepperStep(1);
    generateRandomTeleportationState();
    updateTeleportationUI();
  });

  btnInjectAttack.addEventListener('click', () => {
    executeThreatSimulation();
  });

  // Chernoff Slider Events
  chLengthSlider.addEventListener('input', (e) => {
    state.chLength = parseInt(e.target.value, 10);
    chLengthVal.textContent = state.chLength;
    updateChernoffUI();
  });

  chNoiseSlider.addEventListener('input', (e) => {
    state.chNoise = parseFloat(e.target.value);
    chNoiseVal.textContent = `${state.chNoise.toFixed(3)} (${(state.chNoise * 100).toFixed(1)}%)`;
    updateChernoffUI();
  });

  chTargetEpsSelect.addEventListener('change', (e) => {
    state.chTargetEps = parseFloat(e.target.value);
    updateChernoffUI();
  });

  // Certificate Modal Dialog
  btnExportCert.addEventListener('click', () => {
    const bounds = calculateSecurityBounds(state.chLength, state.chNoise);
    const cert = {
      protocol: "Teleportation-Based Quantum Digital Signature (QDS)",
      security_proof: "Chernoff-Hoeffding Insecurity Bound (Amiri & Wallden et al.)",
      parameters: {
        signature_length_qubits: state.chLength,
        baseline_noise_e0: state.chNoise,
        acceptance_threshold_sa: bounds.sa,
        verification_threshold_sv: bounds.sv,
        safety_margin_delta: bounds.delta
      },
      analytical_bounds: {
        forgery_probability_upper_bound: bounds.pForge,
        false_rejection_rate_upper_bound: bounds.pFRR,
        repudiation_insecurity_bound: bounds.pRep,
        cryptographic_security_level_bits: bounds.secBits
      },
      verdict: "INFORMATION-THEORETICALLY SECURE"
    };

    modalCertContent.innerHTML = `<pre>${JSON.stringify(cert, null, 2)}</pre>`;
    certModal.style.display = 'flex';
  });

  btnCloseModal.addEventListener('click', () => certModal.style.display = 'none');
  btnDismissCert.addEventListener('click', () => certModal.style.display = 'none');
  btnCopyCert.addEventListener('click', () => {
    const jsonText = modalCertContent.innerText;
    navigator.clipboard.writeText(jsonText).then(() => {
      alert('Security Certificate JSON copied to clipboard!');
    });
  });

  // Init
  generateRandomTeleportationState();
  updateTeleportationUI();
  updateChernoffUI();
  executeThreatSimulation();
  setTimeout(triggerMathRender, 100);
});

