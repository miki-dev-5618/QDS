/**
 * ============================================================================
 * Quantum Mathematics & Chernoff-Hoeffding Bound Utilities
 * ============================================================================
 */

export const SYMBOLS = {
  '0_0': '|0⟩',
  '1_0': '|1⟩',
  '0_1': '|+⟩',
  '1_1': '|−⟩'
};

export const DESCRIPTIONS = {
  '0_0': 'Computational Z-basis (Bit 0)',
  '1_0': 'Computational Z-basis (Bit 1)',
  '0_1': 'Diagonal X-basis (Superposition +)',
  '1_1': 'Diagonal X-basis (Superposition −)'
};

/**
 * Pauli Correction Operator from Bell State Measurement Syndromes (m1, m2)
 * m1: Phase syndrome (Z-flip)
 * m2: Bit syndrome (X-flip)
 */
export function getPauliOperator(m1, m2) {
  if (m1 === 0 && m2 === 0) return { op: 'I', label: 'Identity (No-Op)', formula: 'I' };
  if (m1 === 0 && m2 === 1) return { op: 'X', label: 'Bit-Flip (X)', formula: 'X' };
  if (m1 === 1 && m2 === 0) return { op: 'Z', label: 'Phase-Flip (Z)', formula: 'Z' };
  return { op: 'XZ', label: 'Bit+Phase Flip (XZ = -iY)', formula: 'XZ' };
}

/**
 * Determine orthogonal eliminated states for a given measured basis
 */
export function getEliminatedState(srcBit, measBasis) {
  if (measBasis === 0) {
    // Measured in Z basis: eliminate opposite state
    return srcBit === 0 ? '|1⟩' : '|0⟩';
  } else {
    // Measured in X basis: eliminate opposite state
    return srcBit === 0 ? '|−⟩' : '|+⟩';
  }
}

/**
 * Exact Information-Theoretic Security Bounds using Chernoff-Hoeffding Theorem
 * 
 * @param {number} L - Signature length in qubits
 * @param {number} e0 - Baseline physical channel noise (e.g., 0.02 for 2%)
 * @param {number} pForgMin - Minimum error adversary incurs (0.25 for BB84/teleportation)
 */
export function calculateSecurityBounds(L, e0, pForgMin = 0.25) {
  const maxDelta = (pForgMin - e0) / 3.0;
  const delta = Math.max(0.005, maxDelta);
  
  // sa: Signer acceptance threshold
  const sa = e0 + delta;
  
  // sv: Verifier cross-acceptance threshold
  const sv = pForgMin - delta;

  // Upper bound on forgery probability (Hoeffding's inequality): P_forge <= exp(-2 * delta^2 * L)
  const pForge = Math.min(1.0, Math.exp(-2.0 * (delta ** 2) * L));
  
  // False Rejection Rate: P_FRR <= exp(-2 * delta^2 * L)
  const pFRR = pForge;
  
  // Repudiation Insecurity Bound: P_rep <= 2 * exp(-0.5 * (sv - sa)^2 * L)
  const gap = Math.max(0.001, sv - sa);
  const pRep = Math.min(1.0, 2.0 * Math.exp(-0.5 * (gap ** 2) * L));
  
  // Cryptographic security level in bits: -log2(P_forge)
  const secBits = pForge > 0 ? -Math.log2(pForge) : 256.0;

  return {
    sa,
    sv,
    delta,
    gap,
    pForge,
    pFRR,
    pRep,
    secBits: Math.min(secBits, 256.0)
  };
}

/**
 * Minimum required signature length for target security epsilon
 */
export function calculateMinSignatureLength(targetEps, e0, pForgMin = 0.25) {
  const bounds = calculateSecurityBounds(128, e0, pForgMin);
  const lMinForge = Math.ceil(Math.log(1.0 / targetEps) / (2.0 * (bounds.delta ** 2)));
  const lMinRep = Math.ceil(Math.log(2.0 / targetEps) / (0.5 * (bounds.gap ** 2)));
  return Math.max(lMinForge, lMinRep);
}
