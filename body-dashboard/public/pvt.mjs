/* pvt.mjs — PVT-B inspired reaction test (3-min mode, or a fixed number of trials via trialCount) (state machine without DOM; time is passed in from outside).
   Based on Basner et al. 2011 (PVT-B): 3 min, interval 1–4 s incl. 1 s feedback, lapse from 355 ms,
   false start < 100 ms, 30 s without a response counts as a lapse. Not validated, device latency not calibrated. */
import { scorePvt } from './engine.mjs';

export class PvtSession {
  constructor({ durationMs = 180000, feedbackMs = 1000, delayMinMs = 0, delayMaxMs = 3000, timeoutMs = 30000, lapseMs = 355, trialCount = 0, rand = Math.random } = {}) {
    Object.assign(this, { durationMs, feedbackMs, delayMinMs, delayMaxMs, timeoutMs, lapseMs, trialCount, rand });
    this.phase = 'idle'; this.trials = []; this.premature = 0; this.lastRt = null;
  }
  _delay() { return this.delayMinMs + this.rand() * (this.delayMaxMs - this.delayMinMs); }
  start(t) {
    this.t0 = t; this.trials = []; this.premature = 0; this.lastRt = null; this.stimAt = null;
    this.phase = 'delay'; this.at = t + this._delay(); return this;
  }
  progress(t) { if (this.trialCount) return Math.min(1, this.trials.length / this.trialCount); return this.phase === 'idle' ? 0 : Math.min(1, (t - this.t0) / this.durationMs); }
  /** Returns an event: 'stimulus' | 'timeout' | 'delay' | 'done' | null */
  tick(t) {
    if (this.phase === 'delay') {
      if (!this.trialCount && t - this.t0 >= this.durationMs) { this.phase = 'done'; return 'done'; }
      if (t >= this.at) { this.phase = 'stim'; this.stimAt = t; return 'stimulus'; }
    } else if (this.phase === 'stim') {
      if (t - this.stimAt >= this.timeoutMs) { this.trials.push({ rt: null }); this.lastRt = null; this.phase = 'feedback'; this.at = t + this.feedbackMs; return 'timeout'; }
    } else if (this.phase === 'feedback') {
      if (t >= this.at) {
        if (this.trialCount ? this.trials.length >= this.trialCount : t - this.t0 >= this.durationMs) { this.phase = 'done'; return 'done'; }
        this.phase = 'delay'; this.at = t + this._delay(); return 'delay';
      }
    }
    return null;
  }
  /** Tastendruck: 'premature' | 'response' | null */
  press(t) {
    if (this.phase === 'delay') { this.premature++; return 'premature'; }
    if (this.phase === 'stim') {
      const rt = t - this.stimAt; this.trials.push({ rt }); this.lastRt = rt;
      this.phase = 'feedback'; this.at = t + this.feedbackMs; return 'response';
    }
    return null;
  }
  get done() { return this.phase === 'done'; }
  result() { return scorePvt(this.trials, { lapseMs: this.lapseMs, timeoutMs: this.timeoutMs, premature: this.premature }); }
}
