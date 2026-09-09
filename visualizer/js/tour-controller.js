/**
 * ============================================================================
 * Guided Tour & Interactive Story Walkthrough Controller
 * ============================================================================
 */

import { simulateAttack } from './threats.js';
import { state, emit } from './state.js';

export class TourController {
  constructor(options = {}) {
    this.intervalMs = options.intervalMs || 4000;
    this.timer = null;
    this.currentIndex = 0;
    this.isRunning = false;

    this.scenarios = [
      { id: 'authentic', title: '1/7: Baseline Authentic Signature' },
      { id: 'external_forgery', title: '2/7: External Forgery Alert' },
      { id: 'dishonest_verifier', title: '3/7: Dishonest Verifier Alert' },
      { id: 'mitm_intercept', title: '4/7: Quantum Interception Alert' },
      { id: 'repudiation', title: '5/7: Signer Repudiation Alert' },
      { id: 'replay_attack', title: '6/7: Replay & Stale Nonce Alert' },
      { id: 'channel_noise', title: '7/7: Environmental Fiber Noise' }
    ];
  }

  start() {
    this.isRunning = true;
    this.step();
    this.timer = setInterval(() => this.step(), this.intervalMs);
    emit('tourStateChange', { isRunning: true, current: this.getCurrentItem() });
  }

  pause() {
    this.isRunning = false;
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    emit('tourStateChange', { isRunning: false, current: this.getCurrentItem() });
  }

  step() {
    const item = this.scenarios[this.currentIndex];
    const simResult = simulateAttack(item.id);
    emit('tourStep', { index: this.currentIndex, total: this.scenarios.length, item, simResult });
    this.currentIndex = (this.currentIndex + 1) % this.scenarios.length;
  }

  getCurrentItem() {
    return this.scenarios[this.currentIndex];
  }
}
