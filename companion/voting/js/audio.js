// Survivor Voting App - Audio effects using Web Audio API
//
// To preserve atmosphere during Tribal Council and voting, simple sound
// effects are generated on the fly using oscillators. If a browser does
// not support the Web Audio API, these functions will silently fail.

// Lazy-initialize an AudioContext. Web Audio contexts must be created
// in response to a user gesture on some devices, so we defer creation
// until first sound is triggered.
let _audioCtx = null;

function getAudioContext() {
  if (!_audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) {
      _audioCtx = new AudioContext();
    }
  }
  return _audioCtx;
}

/**
 * Play a short percussive tap sound. Useful when a vote is cast.
 */
function playTap() {
  const ctx = getAudioContext();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = 660; // higher pitch
  osc.type = 'square';
  gain.gain.setValueAtTime(0.0, ctx.currentTime);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  // Quick attack and decay
  gain.gain.setValueAtTime(0.4, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1);
  osc.stop(ctx.currentTime + 0.12);
}

/**
 * Play a low drum hit for dramatic reveals.
 */
function playDrum() {
  const ctx = getAudioContext();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.setValueAtTime(80, ctx.currentTime);
  osc.frequency.exponentialRampToValueAtTime(40, ctx.currentTime + 0.3);
  osc.type = 'sine';
  osc.connect(gain);
  gain.connect(ctx.destination);
  gain.gain.setValueAtTime(0.6, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
  osc.start();
  osc.stop(ctx.currentTime + 0.45);
}

/**
 * Play a background theme sound for a specified duration (in seconds).
 * Generates a low, rhythmic drone reminiscent of tribal music.
 */
function playThemeMusic(duration = 5) {
  const ctx = getAudioContext();
  if (!ctx) return;
  const osc1 = ctx.createOscillator();
  const osc2 = ctx.createOscillator();
  const gain = ctx.createGain();
  osc1.type = 'sine';
  osc2.type = 'triangle';
  // Set two frequencies for a beating effect
  osc1.frequency.setValueAtTime(110, ctx.currentTime);
  osc2.frequency.setValueAtTime(112, ctx.currentTime);
  osc1.connect(gain);
  osc2.connect(gain);
  gain.connect(ctx.destination);
  gain.gain.setValueAtTime(0.3, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
  osc1.start();
  osc2.start();
  osc1.stop(ctx.currentTime + duration);
  osc2.stop(ctx.currentTime + duration);
}

// Export theme music function
window.playThemeMusic = playThemeMusic;

// Export to global scope
window.playTap = playTap;
window.playDrum = playDrum;