/**
 * ============================================================================
 * HEDWIG: Teleportation-Based Quantum Digital Signature Simulation Logic
 * ============================================================================
 */

import { state, emit } from './state.js';
import { SYMBOLS, DESCRIPTIONS, getPauliOperator, getEliminatedState, calculateSecurityBounds } from './quantum-math.js';

export function generateTeleportationState() {
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
    // 1. Alice State Preparation (random bit and basis)
    const bit = Math.random() > 0.5 ? 1 : 0;
    const basis = Math.random() > 0.5 ? 1 : 0; // 0 = Z basis, 1 = X basis
    const key = `${bit}_${basis}`;
    state.aliceTokens.push({
      index: i + 1,
      bit,
      basis,
      basisName: basis === 0 ? 'Z-basis' : 'X-basis',
      symbol: SYMBOLS[key],
      desc: DESCRIPTIONS[key]
    });

    // 2. Alice Bell State Measurement Syndromes for Bob and Charlie
    const m1_b = Math.random() > 0.5 ? 1 : 0;
    const m2_b = Math.random() > 0.5 ? 1 : 0;
    const m1_c = Math.random() > 0.5 ? 1 : 0;
    const m2_c = Math.random() > 0.5 ? 1 : 0;
    
    state.aliceSyndromes.push({
      bob: { m1: m1_b, m2: m2_b },
      charlie: { m1: m1_c, m2: m2_c }
    });

    // 3. Pauli Feed-Forward Corrections Applied by Receivers
    const bobP = getPauliOperator(m1_b, m2_b);
    const charlieP = getPauliOperator(m1_c, m2_c);
    state.bobPauli.push(bobP);
    state.charliePauli.push(charlieP);

    // 4. Symmetrisation Swap (Keep or Forward)
    // Symmetrisation ensures neither verifier knows who holds which quantum state
    const bobAction = Math.random() > 0.5 ? 'Keep' : 'Forward';
    const charlieAction = Math.random() > 0.5 ? 'Keep' : 'Forward';

    const bHeld = [];
    const cHeld = [];
    if (bobAction === 'Keep') bHeld.push({ origin: 'Bob Direct', tag: 'Direct' });
    else cHeld.push({ origin: 'Bob Forwarded', tag: 'Fwd-B' });

    if (charlieAction === 'Keep') cHeld.push({ origin: 'Charlie Direct', tag: 'Direct' });
    else bHeld.push({ origin: 'Charlie Forwarded', tag: 'Fwd-C' });

    state.bobHeld.push(bHeld);
    state.charlieHeld.push(cHeld);

    // 5. Orthogonal State Elimination
    // A receiver measures their qubit in a random basis and eliminates the orthogonal eigenstate
    const bElims = [];
    if (bHeld.length > 0) {
      const measBasis = Math.random() > 0.5 ? 1 : 0;
      bElims.push(getEliminatedState(bit, measBasis));
    }

    const cElims = [];
    if (cHeld.length > 0) {
      const measBasis = Math.random() > 0.5 ? 1 : 0;
      cElims.push(getEliminatedState(bit, measBasis));
    }

    state.bobEliminated.push(bElims);
    state.charlieEliminated.push(cElims);
  }

  emit('teleportationUpdated', state);
}

/**
 * Verify verification contradictions against Alice's announced states
 */
export function verifySignature() {
  let bobMismatches = 0;
  let charlieMismatches = 0;
  let bobTotal = 0;
  let charlieTotal = 0;

  for (let i = 0; i < state.signatureLength; i++) {
    const aliceSymbol = state.aliceTokens[i].symbol;
    
    if (state.bobHeld[i].length > 0) {
      bobTotal++;
      if (state.bobEliminated[i].includes(aliceSymbol)) {
        bobMismatches++;
      }
    }

    if (state.charlieHeld[i].length > 0) {
      charlieTotal++;
      if (state.charlieEliminated[i].includes(aliceSymbol)) {
        charlieMismatches++;
      }
    }
  }

  const bRate = bobTotal > 0 ? (bobMismatches / bobTotal) : 0;
  const cRate = charlieTotal > 0 ? (charlieMismatches / charlieTotal) : 0;
  const bounds = calculateSecurityBounds(state.signatureLength, state.baselineNoise);

  return {
    bobMismatches,
    bobTotal,
    bobRate,
    charlieMismatches,
    charlieTotal,
    charlieRate,
    sa: bounds.sa,
    sv: bounds.sv,
    isBobAccepted: bRate <= bounds.sa,
    isCharlieAccepted: cRate <= bounds.sa,
    isProtocolAccepted: bRate <= bounds.sa && cRate <= bounds.sa
  };
}
