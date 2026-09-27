// Quantum Digital Signature (QDS) Simulation Logic

// Protocol state variables
let sigLength = 8;
let abortThresholdPct = 50;
let simulationData = null;
let currentStep = 0;
let selectedPosition = 0;

// States & Bases mapping
const STATES = ['|0⟩', '|1⟩', '|+⟩', '|−⟩'];
const BASES = {
  'Z': ['|0⟩', '|1⟩'],
  'X': ['|+⟩', '|−⟩']
};

// UI Element references
const els = {
  sigLength: document.getElementById('sig-length'),
  abortThreshold: document.getElementById('abort-threshold'),
  btnRandomSim: document.getElementById('btn-random-sim'),
  btnNextStep: document.getElementById('btn-next-step'),
  btnReset: document.getElementById('btn-reset'),
  currentStepBadge: document.getElementById('current-step-badge'),
  stepDescription: document.getElementById('step-description'),
  simulatorView: document.getElementById('simulator-view'),
  aliceStates: document.getElementById('alice-states'),
  bobDecisions: document.getElementById('bob-decisions'),
  charlieDecisions: document.getElementById('charlie-decisions'),
  bobHeld: document.getElementById('bob-held'),
  charlieHeld: document.getElementById('charlie-held'),
  bobElimTable: document.getElementById('bob-elimination-table'),
  charlieElimTable: document.getElementById('charlie-elimination-table'),
  bobAbortProgress: document.getElementById('bob-abort-progress'),
  bobAbortStatus: document.getElementById('bob-abort-status'),
  charlieAbortProgress: document.getElementById('charlie-abort-progress'),
  charlieAbortStatus: document.getElementById('charlie-abort-status'),
  selectMsg: document.getElementById('select-msg'),
  btnVerifyMsg: document.getElementById('btn-verify-msg'),
  bobVerifResult: document.getElementById('bob-verif-result'),
  bobVerifDetails: document.getElementById('bob-verif-details'),
  charlieVerifResult: document.getElementById('charlie-verif-result'),
  charlieVerifDetails: document.getElementById('charlie-verif-details'),
  positionSelectors: document.getElementById('position-selectors'),
  inspectorDetails: document.getElementById('inspector-details'),
  caseDisplay: document.getElementById('case-display'),
  // Tab buttons
  btnCaseKeepKeep: document.getElementById('btn-case-keep-keep'),
  btnCaseKeepForward: document.getElementById('btn-case-keep-forward'),
  btnCaseForwardKeep: document.getElementById('btn-case-forward-keep'),
  btnCaseForwardForward: document.getElementById('btn-case-forward-forward')
};

// Initialize Event Listeners
document.addEventListener('DOMContentLoaded', () => {
  els.btnRandomSim.addEventListener('click', generateRandomSimulation);
  els.btnNextStep.addEventListener('click', runNextStep);
  els.btnReset.addEventListener('click', resetSimulation);
  els.btnVerifyMsg.addEventListener('click', verifyMessage);

  els.btnCaseKeepKeep.addEventListener('click', () => switchCase('keep-keep'));
  els.btnCaseKeepForward.addEventListener('click', () => switchCase('keep-forward'));
  els.btnCaseForwardKeep.addEventListener('click', () => switchCase('forward-keep'));
  els.btnCaseForwardForward.addEventListener('click', () => switchCase('forward-forward'));

  // Load default case explorer tab
  switchCase('keep-keep');
});

// Helper: Get random item from array
function randomChoice(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

// Simulate measurement outcome and return eliminated state
// Returns: { basis, outcome, eliminated }
function simulateMeasurement(state, chosenBasis) {
  const isZ = (chosenBasis === 'Z');
  let outcomeState = '';
  
  if (isZ) {
    if (state === '|0⟩') outcomeState = '|0⟩';
    else if (state === '|1⟩') outcomeState = '|1⟩';
    else outcomeState = randomChoice(['|0⟩', '|1⟩']); // H state measured in Z
  } else {
    if (state === '|+⟩') outcomeState = '|+⟩';
    else if (state === '|−⟩') outcomeState = '|−⟩';
    else outcomeState = randomChoice(['|+⟩', '|−⟩']); // Z state measured in X
  }

  // Orthogonal elimination rule
  let eliminated = '';
  if (outcomeState === '|0⟩') eliminated = '|1⟩';
  else if (outcomeState === '|1⟩') eliminated = '|0⟩';
  else if (outcomeState === '|+⟩') eliminated = '|−⟩';
  else if (outcomeState === '|−⟩') eliminated = '|+⟩';

  return {
    basis: chosenBasis,
    outcome: outcomeState,
    eliminated: eliminated
  };
}

// Step-by-step QDS simulator generator
function generateRandomSimulation() {
  sigLength = parseInt(els.sigLength.value) || 8;
  abortThresholdPct = parseInt(els.abortThreshold.value) || 50;

  // Initialize fresh simulation dataset
  simulationData = {
    // Generate signature components for both possible messages (k=0 and k=1)
    signatures: {
      0: Array.from({ length: sigLength }, () => randomChoice(STATES)),
      1: Array.from({ length: sigLength }, () => randomChoice(STATES))
    },
    // We visually trace message k=0 as the primary example
    activeMsg: 0,
    positions: []
  };

  const activeSig = simulationData.signatures[0];

  for (let i = 0; i < sigLength; i++) {
    const originalState = activeSig[i];
    
    // Bob and Charlie choose whether to Keep (K) or Forward (F)
    const bobAction = randomChoice(['K', 'F']);
    const charlieAction = randomChoice(['K', 'F']);

    // Track state possession after keeping/forwarding
    // Bob initially receives copy 1, Charlie receives copy 2
    let bobHeld = [];
    let charlieHeld = [];

    // Simulate Symmetrisation/Swap stage
    if (bobAction === 'K') {
      bobHeld.push('Bob\'s Original Copy');
    } else {
      charlieHeld.push('Bob\'s Forwarded Copy');
    }

    if (charlieAction === 'K') {
      charlieHeld.push('Charlie\'s Original Copy');
    } else {
      bobHeld.push('Charlie\'s Forwarded Copy');
    }

    // Measurement Phase
    let bobMeasurements = [];
    let charlieMeasurements = [];
    let bobEliminated = [];
    let charlieEliminated = [];

    // Bob measurements
    if (bobHeld.length === 1) {
      const b = randomChoice(['Z', 'X']);
      const m = simulateMeasurement(originalState, b);
      bobMeasurements.push(m);
      bobEliminated.push(m.eliminated);
    } else if (bobHeld.length === 2) {
      // With two copies, measure in both bases to gain maximum information
      const m1 = simulateMeasurement(originalState, 'Z');
      const m2 = simulateMeasurement(originalState, 'X');
      bobMeasurements.push(m1, m2);
      bobEliminated.push(m1.eliminated, m2.eliminated);
    }

    // Charlie measurements
    if (charlieHeld.length === 1) {
      const b = randomChoice(['Z', 'X']);
      const m = simulateMeasurement(originalState, b);
      charlieMeasurements.push(m);
      charlieEliminated.push(m.eliminated);
    } else if (charlieHeld.length === 2) {
      const m1 = simulateMeasurement(originalState, 'Z');
      const m2 = simulateMeasurement(originalState, 'X');
      charlieMeasurements.push(m1, m2);
      charlieEliminated.push(m1.eliminated, m2.eliminated);
    }

    simulationData.positions.push({
      position: i + 1,
      originalState,
      bobAction,
      charlieAction,
      bobHeld,
      charlieHeld,
      bobMeasurements,
      charlieMeasurements,
      bobEliminated,
      charlieEliminated
    });
  }

  // Enable step buttons
  els.btnNextStep.disabled = false;
  els.simulatorView.style.display = 'block';
  currentStep = 0;
  
  runNextStep();
}

function runNextStep() {
  if (!simulationData) return;
  currentStep++;

  switch (currentStep) {
    case 1:
      showAliceGeneration();
      break;
    case 2:
      showDistribution();
      break;
    case 3:
      showSymmetrisation();
      break;
    case 4:
      showMeasurements();
      break;
    case 5:
      checkAbortCondition();
      break;
    case 6:
      showMessagingStage();
      els.btnNextStep.disabled = true; // Complete flow
      break;
  }
}

function resetSimulation() {
  simulationData = null;
  currentStep = 0;
  els.btnNextStep.disabled = true;
  els.simulatorView.style.display = 'none';
  els.currentStepBadge.textContent = 'Idle';
  els.stepDescription.textContent = 'Click "Generate Random Run" to begin the step-by-step QDS simulator!';
  els.positionSelectors.innerHTML = '';
  els.inspectorDetails.innerHTML = '<div class="empty-state">Select a position above to view its detailed quantum journey.</div>';
}

// Render utilities
function showAliceGeneration() {
  els.currentStepBadge.textContent = 'Step 1';
  els.stepDescription.textContent = 'Alice generates private quantum signature states (BB84 states) for message k = 0.';

  // Render Alice signature row
  els.aliceStates.innerHTML = simulationData.positions.map(p => `
    <div class="qstate-circle ${getStateClass(p.originalState)}">
      ${p.originalState}
      <span class="pos-badge">${p.position}</span>
    </div>
  `).join('');

  // Clear subsequent visuals
  els.bobDecisions.innerHTML = '';
  els.charlieDecisions.innerHTML = '';
  els.bobHeld.innerHTML = '';
  els.charlieHeld.innerHTML = '';
  els.bobElimTable.innerHTML = '';
  els.charlieElimTable.innerHTML = '';
  els.bobAbortStatus.textContent = 'Pending...';
  els.charlieAbortStatus.textContent = 'Pending...';
  els.bobAbortProgress.style.width = '0%';
  els.bobAbortProgress.textContent = '0%';
  els.charlieAbortProgress.style.width = '0%';
  els.charlieAbortProgress.textContent = '0%';
  els.bobVerifResult.textContent = 'Pending verification';
  els.bobVerifResult.className = 'verif-result-indicator';
  els.charlieVerifResult.textContent = 'Pending verification';
  els.charlieVerifResult.className = 'verif-result-indicator';
  els.bobVerifDetails.textContent = '';
  els.charlieVerifDetails.textContent = '';

  renderPositionButtons();
}

function showDistribution() {
  els.currentStepBadge.textContent = 'Step 2';
  els.stepDescription.textContent = 'Alice sends copies of the signature elements to Bob and Charlie.';
}

function showSymmetrisation() {
  els.currentStepBadge.textContent = 'Step 3';
  els.stepDescription.textContent = 'Bob and Charlie choose to KEEP or FORWARD elements. This is the symmetrisation step to prevent Alice from cheating later.';

  // Show decisions and states held
  els.bobDecisions.innerHTML = simulationData.positions.map(p => `
    <span class="decision-badge ${p.bobAction === 'K' ? 'keep' : 'forward'}">${p.position}:${p.bobAction}</span>
  `).join('');

  els.charlieDecisions.innerHTML = simulationData.positions.map(p => `
    <span class="decision-badge ${p.charlieAction === 'K' ? 'keep' : 'forward'}">${p.position}:${p.charlieAction}</span>
  `).join('');

  // Show what they hold
  els.bobHeld.innerHTML = simulationData.positions.map(p => `
    <div class="held-item">
      <span>#${p.position}</span>
      <span class="badge">${p.bobHeld.length} Copy</span>
    </div>
  `).join('');

  els.charlieHeld.innerHTML = simulationData.positions.map(p => `
    <div class="held-item">
      <span>#${p.position}</span>
      <span class="badge">${p.charlieHeld.length} Copy</span>
    </div>
  `).join('');
}

function showMeasurements() {
  els.currentStepBadge.textContent = 'Step 4';
  els.stepDescription.textContent = 'Bob and Charlie measure their quantum states, ruling out impossible states (state elimination).';

  // Render Bob elimination table
  els.bobElimTable.innerHTML = simulationData.positions.map(p => `
    <div class="elim-row">
      <span class="elim-pos-label">Pos ${p.position}</span>
      <div class="elim-states-container">
        ${STATES.map(s => {
          const isEliminated = p.bobEliminated.includes(s);
          return `<span class="elim-state-badge ${isEliminated ? 'eliminated' : 'possible'}">${s}</span>`;
        }).join('')}
      </div>
    </div>
  `).join('');

  // Render Charlie elimination table
  els.charlieElimTable.innerHTML = simulationData.positions.map(p => `
    <div class="elim-row">
      <span class="elim-pos-label">Pos ${p.position}</span>
      <div class="elim-states-container">
        ${STATES.map(s => {
          const isEliminated = p.charlieEliminated.includes(s);
          return `<span class="elim-state-badge ${isEliminated ? 'eliminated' : 'possible'}">${s}</span>`;
        }).join('')}
      </div>
    </div>
  `).join('');
}

function checkAbortCondition() {
  els.currentStepBadge.textContent = 'Step 5';
  els.stepDescription.textContent = 'Verifying if Bob and Charlie received enough elements to safely proceed without aborting.';

  const bobCount = simulationData.positions.filter(p => p.bobHeld.length > 0).length;
  const charlieCount = simulationData.positions.filter(p => p.charlieHeld.length > 0).length;

  const bobPct = Math.round((bobCount / sigLength) * 100);
  const charliePct = Math.round((charlieCount / sigLength) * 100);

  // Bob abort check
  els.bobAbortProgress.style.width = `${bobPct}%`;
  els.bobAbortProgress.textContent = `${bobPct}%`;
  if (bobPct >= abortThresholdPct) {
    els.bobAbortStatus.textContent = `ACCEPT (${bobCount}/${sigLength} received)`;
    els.bobAbortStatus.className = 'abort-status-text accept';
  } else {
    els.bobAbortStatus.textContent = `ABORT (Below ${abortThresholdPct}% threshold)`;
    els.bobAbortStatus.className = 'abort-status-text abort';
  }

  // Charlie abort check
  els.charlieAbortProgress.style.width = `${charliePct}%`;
  els.charlieAbortProgress.textContent = `${charliePct}%`;
  if (charliePct >= abortThresholdPct) {
    els.charlieAbortStatus.textContent = `ACCEPT (${charlieCount}/${sigLength} received)`;
    els.charlieAbortStatus.className = 'abort-status-text accept';
  } else {
    els.charlieAbortStatus.textContent = `ABORT (Below ${abortThresholdPct}% threshold)`;
    els.charlieAbortStatus.className = 'abort-status-text abort';
  }
}

function showMessagingStage() {
  els.currentStepBadge.textContent = 'Step 6';
  els.stepDescription.textContent = 'Messaging stage: Alice announces she is signing the selected message. Bob and Charlie verify Alice\'s key against their eliminated states.';
}

function verifyMessage() {
  if (!simulationData) return;
  
  const chosenMsg = parseInt(els.selectMsg.value);
  const aliceProposedSig = simulationData.signatures[chosenMsg];

  // Perform Bob verification
  let bobMismatches = 0;
  let bobTotalVerified = 0;

  // Perform Charlie verification
  let charlieMismatches = 0;
  let charlieTotalVerified = 0;

  simulationData.positions.forEach((p, idx) => {
    const proposedState = aliceProposedSig[idx];

    // Bob only checks positions where he has some information
    if (p.bobHeld.length > 0) {
      bobTotalVerified++;
      if (p.bobEliminated.includes(proposedState)) {
        bobMismatches++;
      }
    }

    // Charlie only checks positions where he has some information
    if (p.charlieHeld.length > 0) {
      charlieTotalVerified++;
      if (p.charlieEliminated.includes(proposedState)) {
        charlieMismatches++;
      }
    }
  });

  // Verify rules: mismatch rate must be extremely low
  // Since we have no channel noise, mismatch rate for correct message should be 0.
  // For incorrect message, the states are random, so Bob/Charlie will detect contradictions.
  const threshold = 1.0; // In noise-free environment, 0 mismatches allowed

  if (bobMismatches === 0) {
    els.bobVerifResult.textContent = 'VALID';
    els.bobVerifResult.className = 'verif-result-indicator success';
  } else {
    els.bobVerifResult.textContent = 'INVALID (FORGED)';
    els.bobVerifResult.className = 'verif-result-indicator fail';
  }
  els.bobVerifDetails.textContent = `Detected ${bobMismatches} contradictions out of ${bobTotalVerified} positions verified.`;

  if (charlieMismatches === 0) {
    els.charlieVerifResult.textContent = 'VALID';
    els.charlieVerifResult.className = 'verif-result-indicator success';
  } else {
    els.charlieVerifResult.textContent = 'INVALID (FORGED)';
    els.charlieVerifResult.className = 'verif-result-indicator fail';
  }
  els.charlieVerifDetails.textContent = `Detected ${charlieMismatches} contradictions out of ${charlieTotalVerified} positions verified.`;
}

// Render the position tabs for element inspector
function renderPositionButtons() {
  els.positionSelectors.innerHTML = simulationData.positions.map(p => `
    <button class="pos-btn" onclick="inspectPosition(${p.position - 1})">${p.position}</button>
  `).join('');
  
  inspectPosition(0);
}

window.inspectPosition = function(idx) {
  selectedPosition = idx;
  const p = simulationData.positions[idx];
  
  // Highlight active selector
  const buttons = els.positionSelectors.querySelectorAll('.pos-btn');
  buttons.forEach((btn, bIdx) => {
    if (bIdx === idx) btn.classList.add('active');
    else btn.classList.remove('active');
  });

  let bobMeasuresHTML = p.bobMeasurements.map((m, mIdx) => `
    <p><strong>Measurement ${mIdx + 1}:</strong> basis = ${m.basis}, outcome = ${m.outcome} ➔ eliminates state <strong>${m.eliminated}</strong></p>
  `).join('');
  if (p.bobMeasurements.length === 0) bobMeasuresHTML = '<p>No copy received ➔ No measurements made</p>';

  let charlieMeasuresHTML = p.charlieMeasurements.map((m, mIdx) => `
    <p><strong>Measurement ${mIdx + 1}:</strong> basis = ${m.basis}, outcome = ${m.outcome} ➔ eliminates state <strong>${m.eliminated}</strong></p>
  `).join('');
  if (p.charlieMeasurements.length === 0) charlieMeasuresHTML = '<p>No copy received ➔ No measurements made</p>';

  els.inspectorDetails.innerHTML = `
    <div class="inspector-flow">
      <div class="inspector-step">
        <div class="step-num-icon">1</div>
        <div class="step-info">
          <h5>Alice Generates Quantum State</h5>
          <p>Alice generated state <strong>${p.originalState}</strong> for position ${p.position}.</p>
        </div>
      </div>
      <div class="inspector-step">
        <div class="step-num-icon">2</div>
        <div class="step-info">
          <h5>Keep / Forward Symmetrisation Action</h5>
          <p>Bob chose to <strong>${p.bobAction === 'K' ? 'KEEP' : 'FORWARD'}</strong>, Charlie chose to <strong>${p.charlieAction === 'K' ? 'KEEP' : 'FORWARD'}</strong>.</p>
        </div>
      </div>
      <div class="inspector-step">
        <div class="step-num-icon">3</div>
        <div class="step-info">
          <h5>Final Copy Possession</h5>
          <p>Bob holds: <strong>${p.bobHeld.length} copy</strong> (${p.bobHeld.join(' + ') || 'none'}).</p>
          <p>Charlie holds: <strong>${p.charlieHeld.length} copy</strong> (${p.charlieHeld.join(' + ') || 'none'}).</p>
        </div>
      </div>
      <div class="inspector-step">
        <div class="step-num-icon">4</div>
        <div class="step-info">
          <h5>Quantum Measurements & Elimination Outcomes</h5>
          <div>
            <h6>Bob:</h6>
            ${bobMeasuresHTML}
            <h6>Charlie:</h6>
            ${charlieMeasuresHTML}
          </div>
        </div>
      </div>
    </div>
  `;
};

// Deterministic Case Explorer switch
window.switchCase = function(caseType) {
  const tabs = document.querySelectorAll('.cases-tabs .tab-btn');
  tabs.forEach(tab => {
    tab.classList.remove('active');
  });

  let title = '';
  let bobPossesses = '';
  let charliePossesses = '';
  let bobMeasureRule = '';
  let charlieMeasureRule = '';
  let description = '';

  switch (caseType) {
    case 'keep-keep':
      document.getElementById('btn-case-keep-keep').classList.add('active');
      title = 'Bob Keeps & Charlie Keeps';
      bobPossesses = '1 copy (original Bob copy)';
      charliePossesses = '1 copy (original Charlie copy)';
      bobMeasureRule = 'Bob performs exactly 1 measurement in a randomly chosen basis (Z or X), eliminating 1 state.';
      charlieMeasureRule = 'Charlie performs exactly 1 measurement in a randomly chosen basis (Z or X), eliminating 1 state.';
      description = 'Both players keep their original states. Each can perform exactly one measurement. Neither receives a second copy, meaning neither can perform two measurements to eliminate two states.';
      break;
    case 'keep-forward':
      document.getElementById('btn-case-keep-forward').classList.add('active');
      title = 'Bob Keeps & Charlie Forwards';
      bobPossesses = '2 copies (original Bob copy + Charlie forwarded copy)';
      charliePossesses = '0 copies';
      bobMeasureRule = 'Bob performs 2 measurements (one in Z basis and one in X basis), eliminating exactly 2 states.';
      charlieMeasureRule = 'Charlie has 0 copies, so he cannot perform any measurements or eliminate any states.';
      description = 'Charlie forwards his state to Bob. Since Bob now has two copies of the state, he can measure one in the Z basis and one in the X basis. This allows Bob to rule out two states, making his signature verification more robust.';
      break;
    case 'forward-keep':
      document.getElementById('btn-case-forward-keep').classList.add('active');
      title = 'Bob Forwards & Charlie Keeps';
      bobPossesses = '0 copies';
      charliePossesses = '2 copies (original Charlie copy + Bob forwarded copy)';
      bobMeasureRule = 'Bob has 0 copies, so he cannot perform any measurements or eliminate any states.';
      charlieMeasureRule = 'Charlie performs 2 measurements (one in Z basis and one in X basis), eliminating exactly 2 states.';
      description = 'Bob forwards his state to Charlie. Charlie now holds two copies, letting Charlie perform two orthogonal measurements to eliminate two incorrect states.';
      break;
    case 'forward-forward':
      document.getElementById('btn-case-forward-forward').classList.add('active');
      title = 'Bob Forwards & Charlie Forwards';
      bobPossesses = '1 copy (Charlie forwarded copy)';
      charliePossesses = '1 copy (Bob forwarded copy)';
      bobMeasureRule = 'Bob performs exactly 1 measurement in a randomly chosen basis (Z or X), eliminating 1 state.';
      charlieMeasureRule = 'Charlie performs exactly 1 measurement in a randomly chosen basis (Z or X), eliminating 1 state.';
      description = 'Both players forward their states to each other. They end up swapping states, so each still holds exactly 1 copy (the other player\'s copy). Each player can perform exactly 1 measurement.';
      break;
  }

  els.caseDisplay.innerHTML = `
    <div class="case-grid">
      <div class="case-side">
        <h4>${title}</h4>
        <p><strong>Description:</strong> ${description}</p>
      </div>
      <div class="case-side">
        <div class="outcome-list">
          <div class="outcome-item">
            <h5>Bob's State Possession</h5>
            <p>${bobPossesses}</p>
            <p><strong>Measurement Action:</strong> ${bobMeasureRule}</p>
          </div>
          <div class="outcome-item">
            <h5>Charlie's State Possession</h5>
            <p>${charliePossesses}</p>
            <p><strong>Measurement Action:</strong> ${charlieMeasureRule}</p>
          </div>
        </div>
      </div>
    </div>
  `;
};

// CSS Class picker
function getStateClass(state) {
  if (state === '|0⟩') return 'state-0';
  if (state === '|1⟩') return 'state-1';
  if (state === '|+⟩') return 'state-plus';
  if (state === '|−⟩') return 'state-minus';
  return '';
}
