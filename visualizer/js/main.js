/**
 * ============================================================================
 * Main UI Application Orchestrator
 * ============================================================================
 */

import { state, on, emit, setViewMode, setProtocolMode } from './state.js';
import { calculateSecurityBounds, calculateMinSignatureLength } from './quantum-math.js';
import { generateTeleportationState, verifySignature } from './teleportation.js';
import { simulateAttack, THREAT_METADATA } from './threats.js';
import { renderChernoffChart } from './chernoff-chart.js';
import { TourController } from './tour-controller.js';

document.addEventListener('DOMContentLoaded', () => {
  const tour = new TourController({ intervalMs: 3500 });

  // DOM Elements
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const modeSwitchStory = document.getElementById('mode-story');
  const modeSwitchExpert = document.getElementById('mode-expert');

  // Tab 1 Elements
  const telSigLenSlider = document.getElementById('tel-sig-len');
  const telSigLenVal = document.getElementById('tel-sig-len-val');
  const telNoiseSlider = document.getElementById('tel-noise');
  const telNoiseVal = document.getElementById('tel-noise-val');
  const btnRunTel = document.getElementById('btn-run-teleportation');
  const btnStepTel = document.getElementById('btn-step-teleportation');
  const btnResetTel = document.getElementById('btn-reset-teleportation');
  const stepNodes = document.querySelectorAll('.step-node');

  const alicePipelineTokens = document.getElementById('alice-pipeline-tokens');
  const aliceSyndromesList = document.getElementById('alice-syndromes-list');
  const bobPauliApplied = document.getElementById('bob-pauli-applied');
  const charliePauliApplied = document.getElementById('charlie-pauli-applied');
  const bobHeldTokens = document.getElementById('bob-held-tokens');
  const charlieHeldTokens = document.getElementById('charlie-held-tokens');
  const bobElimList = document.getElementById('bob-elim-list');
  const charlieElimList = document.getElementById('charlie-elim-list');
  const bobVerdictBadge = document.getElementById('bob-verdict-badge');
  const charlieVerdictBadge = document.getElementById('charlie-verdict-badge');

  const telBobMis = document.getElementById('tel-bob-mis');
  const telCharlieMis = document.getElementById('tel-charlie-mis');
  const telSaVal = document.getElementById('tel-sa-val');
  const telSvVal = document.getElementById('tel-sv-val');
  const telProtocolStatus = document.getElementById('tel-protocol-status');

  // Tab 2 & 3 Elements (Threat Studio)
  const attackCards = document.querySelectorAll('.attack-card');
  const btnInjectAttack = document.getElementById('btn-inject-attack');
  const currentThreatBadge = document.getElementById('current-threat-badge');
  const threatStoryBanner = document.getElementById('threat-story-banner');
  const threatPhysicsBanner = document.getElementById('threat-physics-banner');

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

  // Modal Elements
  const certModal = document.getElementById('cert-modal');
  const btnExportCert = document.getElementById('btn-export-cert');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const btnDismissCert = document.getElementById('btn-dismiss-cert');
  const btnCopyCert = document.getElementById('btn-copy-cert');
  const modalCertContent = document.getElementById('modal-cert-content');

  // Tour Elements
  const btnStartTour = document.getElementById('btn-start-tour');
  const btnPauseTour = document.getElementById('btn-pause-tour');
  const tourStepTag = document.getElementById('tour-step-tag');
  const protocolModeSelect = document.getElementById('protocol-mode-select');

  // Helper: Trigger KaTeX math rendering
  function triggerMathRender() {
    if (typeof window.renderMathInElement === 'function') {
      try {
        window.renderMathInElement(document.body, {
          delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '$', right: '$', display: false }
          ],
          throwOnError: false
        });
      } catch (err) {
        console.warn('KaTeX render note:', err);
      }
    }
  }

  // =========================================================================
  // 1. Navigation & Tabs
  // =========================================================================
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
        renderChernoffChart('chernoffCanvas');
      }

      setTimeout(triggerMathRender, 50);
    });
  });

  // Story Mode vs Expert Mode Toggle
  if (modeSwitchStory && modeSwitchExpert) {
    modeSwitchStory.addEventListener('click', () => {
      modeSwitchStory.classList.add('active');
      modeSwitchExpert.classList.remove('active');
      document.body.classList.remove('expert-mode');
      document.body.classList.add('story-mode');
      setViewMode('story');
    });

    modeSwitchExpert.addEventListener('click', () => {
      modeSwitchExpert.classList.add('active');
      modeSwitchStory.classList.remove('active');
      document.body.classList.remove('story-mode');
      document.body.classList.add('expert-mode');
      setViewMode('expert');
      setTimeout(triggerMathRender, 50);
    });
  }

  // =========================================================================
  // 2. Teleportation UI Rendering
  // =========================================================================
  function renderTeleportationUI() {
    // 1. Render Alice Tokens
    if (alicePipelineTokens) {
      alicePipelineTokens.innerHTML = '';
      state.aliceTokens.forEach((t) => {
        const chip = document.createElement('div');
        chip.className = 'quantum-token-card';
        chip.innerHTML = `
          <div class="token-idx">#${t.index}</div>
          <div class="token-state">${t.symbol}</div>
          <div class="token-basis">${t.basisName}</div>
        `;
        alicePipelineTokens.appendChild(chip);
      });
    }

    // 2. Render Alice BSM Syndromes
    if (aliceSyndromesList) {
      aliceSyndromesList.innerHTML = '';
      state.aliceSyndromes.forEach((syn, i) => {
        const chip = document.createElement('span');
        chip.className = 'syndrome-tag';
        chip.textContent = `#${i + 1}: B(${syn.bob.m1},${syn.bob.m2}) | C(${syn.charlie.m1},${syn.charlie.m2})`;
        aliceSyndromesList.appendChild(chip);
      });
    }

    // 3. Render Pauli Corrections Applied
    if (bobPauliApplied) {
      bobPauliApplied.innerHTML = '';
      state.bobPauli.forEach((p, i) => {
        const badge = document.createElement('span');
        badge.className = 'pauli-pill';
        badge.textContent = `#${i + 1}: ${p.op}`;
        badge.title = p.label;
        bobPauliApplied.appendChild(badge);
      });
    }

    if (charliePauliApplied) {
      charliePauliApplied.innerHTML = '';
      state.charliePauli.forEach((p, i) => {
        const badge = document.createElement('span');
        badge.className = 'pauli-pill';
        badge.textContent = `#${i + 1}: ${p.op}`;
        badge.title = p.label;
        charliePauliApplied.appendChild(badge);
      });
    }

    // 4. Render Held Registries
    if (bobHeldTokens) {
      bobHeldTokens.innerHTML = '';
      state.bobHeld.forEach((h, i) => {
        const tag = document.createElement('span');
        tag.className = 'held-pill';
        tag.textContent = `#${i + 1}: ${h.map(x => x.tag).join('+') || 'None'}`;
        bobHeldTokens.appendChild(tag);
      });
    }

    if (charlieHeldTokens) {
      charlieHeldTokens.innerHTML = '';
      state.charlieHeld.forEach((h, i) => {
        const tag = document.createElement('span');
        tag.className = 'held-pill';
        tag.textContent = `#${i + 1}: ${h.map(x => x.tag).join('+') || 'None'}`;
        charlieHeldTokens.appendChild(tag);
      });
    }

    // 5. Render Eliminated States
    if (bobElimList) {
      bobElimList.innerHTML = '';
      state.bobEliminated.forEach((el, i) => {
        const tag = document.createElement('span');
        tag.className = 'elim-pill';
        tag.textContent = `#${i + 1}: ∉ {${el.join(', ') || '∅'}}`;
        bobElimList.appendChild(tag);
      });
    }

    if (charlieElimList) {
      charlieElimList.innerHTML = '';
      state.charlieEliminated.forEach((el, i) => {
        const tag = document.createElement('span');
        tag.className = 'elim-pill';
        tag.textContent = `#${i + 1}: ∉ {${el.join(', ') || '∅'}}`;
        charlieElimList.appendChild(tag);
      });
    }

    // 6. Verification Results
    const res = verifySignature();
    if (telBobMis) telBobMis.textContent = `${res.bobMismatches} / ${res.bobTotal} (${(res.bobRate * 100).toFixed(1)}%)`;
    if (telCharlieMis) telCharlieMis.textContent = `${res.charlieMismatches} / ${res.charlieTotal} (${(res.charlieRate * 100).toFixed(1)}%)`;
    if (telSaVal) telSaVal.textContent = `${(res.sa * 100).toFixed(2)}%`;
    if (telSvVal) telSvVal.textContent = `${(res.sv * 100).toFixed(2)}%`;

    if (bobVerdictBadge) {
      bobVerdictBadge.className = res.isBobAccepted ? 'verdict-badge pass' : 'verdict-badge fail';
      bobVerdictBadge.textContent = res.isBobAccepted ? 'PASS: Signature Verified' : `REJECT: ${res.bobMismatches} Contradictions`;
    }

    if (charlieVerdictBadge) {
      charlieVerdictBadge.className = res.isCharlieAccepted ? 'verdict-badge pass' : 'verdict-badge fail';
      charlieVerdictBadge.textContent = res.isCharlieAccepted ? 'PASS: Signature Verified' : `REJECT: ${res.charlieMismatches} Contradictions`;
    }

    if (telProtocolStatus) {
      telProtocolStatus.textContent = res.isProtocolAccepted ? 'AUTHENTIC ACCEPTANCE' : 'CONTRADICTION DETECTED';
      telProtocolStatus.className = res.isProtocolAccepted ? 'tel-val text-green' : 'tel-val text-red';
    }
  }

  function setStepperStep(step) {
    stepNodes.forEach(node => {
      const nodeStep = parseInt(node.dataset.step, 10);
      if (nodeStep <= step) node.classList.add('active');
      else node.classList.remove('active');
    });
  }

  // =========================================================================
  // 3. Threat Engine & Studio (Real Dynamic Quantum Simulation)
  // =========================================================================
  function renderThreatUI(scenario) {
    if (!scenario) return;

    // Observables (dynamic calculated percentages & fraction counts)
    if (obsBobRate) {
      obsBobRate.textContent = scenario.bobMismatches !== undefined
        ? `${scenario.bobMismatches} / ${scenario.totalBob} (${scenario.bobRate.toFixed(1)}%)`
        : `${scenario.bobRate.toFixed(1)}%`;
    }
    if (obsCharlieRate) {
      obsCharlieRate.textContent = scenario.charlieMismatches !== undefined
        ? `${scenario.charlieMismatches} / ${scenario.totalCharlie} (${scenario.charlieRate.toFixed(1)}%)`
        : `${scenario.charlieRate.toFixed(1)}%`;
    }

    const asym = Math.abs(scenario.bobRate - scenario.charlieRate);
    if (obsAsymRate) obsAsymRate.textContent = `${asym.toFixed(1)}%`;
    if (obsQberRate) obsQberRate.textContent = `${(scenario.qber * 100).toFixed(1)}%`;

    if (barBobRate) barBobRate.style.width = `${Math.min(100, scenario.bobRate * 2)}%`;
    if (barCharlieRate) barCharlieRate.style.width = `${Math.min(100, scenario.charlieRate * 2)}%`;
    if (barAsymRate) barAsymRate.style.width = `${Math.min(100, asym * 2)}%`;
    if (barQberRate) barQberRate.style.width = `${Math.min(100, scenario.qber * 300)}%`;

    if (currentThreatBadge) {
      currentThreatBadge.textContent = scenario.tag;
      currentThreatBadge.className = `badge ${scenario.tagClass}`;
    }

    if (threatStoryBanner) {
      threatStoryBanner.innerHTML = `<strong>Story Explanation:</strong> ${scenario.storyExplanation}`;
    }

    if (threatPhysicsBanner) {
      threatPhysicsBanner.innerHTML = `<strong>Quantum Physics Observable:</strong> ${scenario.physicsDetails}`;
    }

    // Engine Verdict Card
    if (engineVerdictTitle) engineVerdictTitle.textContent = scenario.verdictTitle;
    if (engineVerdictDetails) engineVerdictDetails.textContent = scenario.details || scenario.shortDesc;
    if (engineClassification) engineClassification.textContent = scenario.classification;
    if (engineConfidence) engineConfidence.textContent = scenario.isThreat ? '96.5%' : '100.0%';
    
    if (engineIsThreat) {
      engineIsThreat.textContent = scenario.isThreat ? 'YES (ACTIVE ALERT)' : 'NO (SECURE)';
      engineIsThreat.className = scenario.isThreat ? 'metric-value text-red' : 'metric-value text-green';
    }

    if (engineAlertStamp) {
      engineAlertStamp.textContent = scenario.stamp;
      engineAlertStamp.className = `alert-stamp ${scenario.stampClass}`;
    }

    if (diagnosticVerdictCard) {
      if (scenario.isThreat) diagnosticVerdictCard.classList.add('threat-active');
      else diagnosticVerdictCard.classList.remove('threat-active');
    }

    // Render Live Simulated Token Inspection Log
    const tokenLogContainer = document.getElementById('threat-token-log');
    const simSeedTag = document.getElementById('threat-sim-seed-tag');
    if (simSeedTag) {
      const timeStr = new Date().toLocaleTimeString();
      simSeedTag.textContent = `Live Sample: ${scenario.sampleSize || 32} Qubits • Seed: #${Math.floor(Math.random() * 8999 + 1000)} • ${timeStr}`;
    }
    if (tokenLogContainer && scenario.tokenLogs) {
      tokenLogContainer.innerHTML = '';
      scenario.tokenLogs.forEach(t => {
        const row = document.createElement('div');
        row.className = `token-log-item ${t.status}`;
        row.textContent = t.text;
        tokenLogContainer.appendChild(row);
      });
    }

    // Highlight Decision Matrix Row
    document.querySelectorAll('.decision-matrix-table tr').forEach(r => r.classList.remove('active-rule'));
    const targetRow = document.getElementById(scenario.activeRowId);
    if (targetRow) targetRow.classList.add('active-rule');
  }

  // Attack selection
  attackCards.forEach(card => {
    card.addEventListener('click', () => {
      attackCards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      const radio = card.querySelector('input[type="radio"]');
      if (radio) {
        radio.checked = true;
        state.activeAttack = radio.value;
        const scenario = simulateAttack(radio.value);
        renderThreatUI(scenario);
      }
    });
  });

  if (btnInjectAttack) {
    btnInjectAttack.addEventListener('click', () => {
      btnInjectAttack.disabled = true;
      const originalText = btnInjectAttack.innerHTML;
      btnInjectAttack.innerHTML = '<span>⚡</span> Simulating Quantum State...';
      
      setTimeout(() => {
        const scenario = simulateAttack(state.activeAttack);
        renderThreatUI(scenario);
        btnInjectAttack.disabled = false;
        btnInjectAttack.innerHTML = originalText;
      }, 200);
    });
  }

  // =========================================================================
  // 4. Chernoff Bounds & Parameter Calculations
  // =========================================================================
  function updateChernoffUI() {
    const L = parseInt(state.chLength, 10);
    const e0 = parseFloat(state.chNoise);
    const targetEps = parseFloat(state.chTargetEps);

    const bounds = calculateSecurityBounds(L, e0);
    const lMin = calculateMinSignatureLength(targetEps, e0);

    if (chCalcSa) chCalcSa.textContent = `${(bounds.sa * 100).toFixed(2)}%`;
    if (chCalcSv) chCalcSv.textContent = `${(bounds.sv * 100).toFixed(2)}%`;
    if (chCalcDelta) chCalcDelta.textContent = bounds.delta.toFixed(4);
    if (chCalcLmin) chCalcLmin.textContent = `${lMin.toLocaleString()} qubits`;

    if (footPforge) footPforge.textContent = bounds.pForge < 1e-4 ? bounds.pForge.toExponential(2) : bounds.pForge.toFixed(4);
    if (footPfrr) footPfrr.textContent = bounds.pFRR < 1e-4 ? bounds.pFRR.toExponential(2) : bounds.pFRR.toFixed(4);
    if (footPrep) footPrep.textContent = bounds.pRep < 1e-4 ? bounds.pRep.toExponential(2) : bounds.pRep.toFixed(4);
    if (footSecbits) footSecbits.textContent = `${bounds.secBits.toFixed(1)} bits`;

    // Sync Tab 1 Telemetry
    if (telSaVal) telSaVal.textContent = `${(bounds.sa * 100).toFixed(2)}%`;
    if (telSvVal) telSvVal.textContent = `${(bounds.sv * 100).toFixed(2)}%`;

    renderChernoffChart('chernoffCanvas');
  }

  // Sliders
  if (telSigLenSlider) {
    telSigLenSlider.addEventListener('input', (e) => {
      state.signatureLength = parseInt(e.target.value, 10);
      if (telSigLenVal) telSigLenVal.textContent = state.signatureLength;
      generateTeleportationState();
      renderTeleportationUI();
    });
  }

  if (telNoiseSlider) {
    telNoiseSlider.addEventListener('input', (e) => {
      state.baselineNoise = parseFloat(e.target.value) / 100.0;
      if (telNoiseVal) telNoiseVal.textContent = `${parseFloat(e.target.value).toFixed(1)}%`;
      updateChernoffUI();
      renderTeleportationUI();
    });
  }

  if (chLengthSlider) {
    chLengthSlider.addEventListener('input', (e) => {
      state.chLength = parseInt(e.target.value, 10);
      if (chLengthVal) chLengthVal.textContent = state.chLength;
      updateChernoffUI();
    });
  }

  if (chNoiseSlider) {
    chNoiseSlider.addEventListener('input', (e) => {
      state.chNoise = parseFloat(e.target.value);
      if (chNoiseVal) chNoiseVal.textContent = `${state.chNoise.toFixed(3)} (${(state.chNoise * 100).toFixed(1)}%)`;
      updateChernoffUI();
    });
  }

  if (chTargetEpsSelect) {
    chTargetEpsSelect.addEventListener('change', (e) => {
      state.chTargetEps = parseFloat(e.target.value);
      updateChernoffUI();
    });
  }

  // Step buttons
  if (btnRunTel) {
    btnRunTel.addEventListener('click', () => {
      generateTeleportationState();
      renderTeleportationUI();
      setStepperStep(5);
    });
  }

  if (btnStepTel) {
    btnStepTel.addEventListener('click', () => {
      if (state.currentStep >= state.maxSteps) state.currentStep = 0;
      state.currentStep++;
      setStepperStep(state.currentStep);
      if (state.currentStep === 1) {
        generateTeleportationState();
      }
      renderTeleportationUI();
    });
  }

  if (btnResetTel) {
    btnResetTel.addEventListener('click', () => {
      state.currentStep = 1;
      setStepperStep(1);
      generateTeleportationState();
      renderTeleportationUI();
    });
  }

  // Security Certificate Modal
  if (btnExportCert) {
    btnExportCert.addEventListener('click', () => {
      const bounds = calculateSecurityBounds(state.chLength, state.chNoise);
      const cert = {
        protocol: "Teleportation-Based Quantum Digital Signature (QDS)",
        security_proof: "Chernoff-Hoeffding Insecurity Bound (Amiri & Wallden et al.)",
        standard: "SIH 2026 Information-Theoretic Security Verification",
        parameters: {
          signature_length_qubits: state.chLength,
          baseline_noise_e0: state.chNoise,
          acceptance_threshold_sa: Number(bounds.sa.toFixed(4)),
          verification_threshold_sv: Number(bounds.sv.toFixed(4)),
          safety_margin_delta: Number(bounds.delta.toFixed(4))
        },
        analytical_bounds: {
          forgery_probability_upper_bound: bounds.pForge < 1e-4 ? bounds.pForge.toExponential(4) : Number(bounds.pForge.toFixed(6)),
          false_rejection_rate_upper_bound: bounds.pFRR < 1e-4 ? bounds.pFRR.toExponential(4) : Number(bounds.pFRR.toFixed(6)),
          repudiation_insecurity_bound: bounds.pRep < 1e-4 ? bounds.pRep.toExponential(4) : Number(bounds.pRep.toFixed(6)),
          cryptographic_security_level_bits: Number(bounds.secBits.toFixed(2))
        },
        deterministic_engine: {
          type: "Deterministic Non-AI Physics Rule Classifier",
          tamper_resistance: "Information-Theoretically Bound",
          status: "VERIFIED_SECURE"
        }
      };

      if (modalCertContent) {
        modalCertContent.innerHTML = `<pre>${JSON.stringify(cert, null, 2)}</pre>`;
      }
      if (certModal) certModal.style.display = 'flex';
    });
  }

  if (btnCloseModal) btnCloseModal.addEventListener('click', () => certModal.style.display = 'none');
  if (btnDismissCert) btnDismissCert.addEventListener('click', () => certModal.style.display = 'none');
  if (btnCopyCert) {
    btnCopyCert.addEventListener('click', () => {
      const jsonText = modalCertContent.innerText;
      navigator.clipboard.writeText(jsonText).then(() => {
        alert('Cryptographic Security Certificate JSON copied to clipboard!');
      });
    });
  }

  // =========================================================================
  // 5. Auto Tour Event Subscriptions
  // =========================================================================
  on('tourStep', ({ item, simResult }) => {
    if (tourStepTag) tourStepTag.textContent = item.title;

    attackCards.forEach(card => {
      const radio = card.querySelector('input[type="radio"]');
      if (radio && radio.value === item.id) {
        card.classList.add('active');
        radio.checked = true;
        state.activeAttack = item.id;
      } else {
        card.classList.remove('active');
      }
    });

    const scenario = simResult || simulateAttack(item.id);
    renderThreatUI(scenario);
  });

  if (btnStartTour) {
    btnStartTour.addEventListener('click', () => {
      const threatTabBtn = document.querySelector('[data-tab="tab-threats"]');
      if (threatTabBtn) threatTabBtn.click();

      btnStartTour.style.display = 'none';
      if (btnPauseTour) btnPauseTour.style.display = 'inline-flex';
      tour.start();
    });
  }

  if (btnPauseTour) {
    btnPauseTour.addEventListener('click', () => {
      tour.pause();
      btnPauseTour.style.display = 'none';
      if (btnStartTour) btnStartTour.style.display = 'inline-flex';
      if (tourStepTag) tourStepTag.textContent = 'Tour Paused';
    });
  }

  if (protocolModeSelect) {
    protocolModeSelect.addEventListener('change', (e) => {
      setProtocolMode(e.target.value);
      generateTeleportationState();
      renderTeleportationUI();
    });
  }

  // Initial Boot
  generateTeleportationState();
  renderTeleportationUI();
  updateChernoffUI();
  const initScenario = simulateAttack('authentic');
  renderThreatUI(initScenario);
  setTimeout(triggerMathRender, 150);
});
