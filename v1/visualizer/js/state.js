/**
 * ============================================================================
 * Reactive Simulation State Store
 * ============================================================================
 */

export const state = {
  // Mode: 'story' (intuitive plain English) or 'expert' (KaTeX/Dirac math)
  viewMode: 'story',
  
  // Protocol: 'teleportation' or 'direct'
  protocolMode: 'teleportation',

  // Teleportation Parameters
  signatureLength: 12,
  baselineNoise: 0.02,
  currentStep: 1,
  maxSteps: 5,

  // Quantum Data Pools
  aliceTokens: [],      // Array of { bit, basis, symbol, desc }
  aliceSyndromes: [],   // Array of { bob: {m1, m2}, charlie: {m1, m2} }
  bobHeld: [],          // Array of { count, origin }
  charlieHeld: [],
  bobPauli: [],         // Array of 'I' | 'X' | 'Z' | 'XZ'
  charliePauli: [],
  bobEliminated: [],    // Array of string[]
  charlieEliminated: [],

  // Attack & Threat State
  activeAttack: 'authentic',
  
  // Chernoff Security Bound Parameters
  chLength: 128,
  chNoise: 0.02,
  chTargetEps: 1e-6
};

// Simple Event Bus for State Subscriptions
const listeners = new Map();

export function on(event, callback) {
  if (!listeners.has(event)) {
    listeners.set(event, []);
  }
  listeners.get(event).push(callback);
}

export function emit(event, data) {
  if (listeners.has(event)) {
    listeners.get(event).forEach(cb => cb(data));
  }
}

export function setViewMode(mode) {
  state.viewMode = mode;
  emit('viewModeChange', mode);
}

export function setProtocolMode(mode) {
  state.protocolMode = mode;
  emit('protocolModeChange', mode);
}
