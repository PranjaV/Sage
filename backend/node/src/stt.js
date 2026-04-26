// Streaming STT — accepts pcm16 mono 16kHz chunks, posts to gpt-4o-mini-transcribe.
// Emits 'partial' (mid-utterance) and 'final' transcripts.

import { EventEmitter } from 'node:events';
import wav from 'node-wav';

const SAMPLE_RATE = 16_000;
const SILENCE_RMS = 350;            // pcm16 amplitude RMS gate
const SILENCE_HOLD_MS = 700;
const MAX_UTTERANCE_MS = 8_000;
const PARTIAL_AT_MS = 1_500;
const MIN_AUDIO_MS = 250;            // ignore stray sub-quarter-second blips

export class StreamingSTT extends EventEmitter {
  constructor({ apiKey, sessionId } = {}) {
    super();
    this.apiKey = apiKey || process.env.OPENAI_API_KEY;
    this.sessionId = sessionId || null;
    this._buffers = [];
    this._totalBytes = 0;
    this._startedAt = null;
    this._lastVoiceAt = null;
    this._partialFired = false;
    this._silenceTimer = null;
    this._maxTimer = null;
    this._closed = false;
  }

  push(buf) {
    if (this._closed) return;
    if (!Buffer.isBuffer(buf)) buf = Buffer.from(buf);
    if (buf.byteLength < 2) return;

    const now = Date.now();
    if (!this._startedAt) {
      this._startedAt = now;
      this._maxTimer = setTimeout(() => this._flush('max-duration'), MAX_UTTERANCE_MS);
    }

    this._buffers.push(buf);
    this._totalBytes += buf.byteLength;

    const rms = pcm16Rms(buf);
    const isVoice = rms >= SILENCE_RMS;

    if (isVoice) {
      this._lastVoiceAt = now;
      if (this._silenceTimer) {
        clearTimeout(this._silenceTimer);
        this._silenceTimer = null;
      }
      // Fire a single partial mid-utterance once we've heard ~1.5s of audio.
      const elapsed = now - this._startedAt;
      if (!this._partialFired && elapsed >= PARTIAL_AT_MS) {
        this._partialFired = true;
        this._fakePartial();
      }
    } else if (this._lastVoiceAt && !this._silenceTimer) {
      this._silenceTimer = setTimeout(() => this._flush('silence'), SILENCE_HOLD_MS);
    }
  }

  /** Mid-utterance: emit a placeholder `partial`. The real text only lands at `final`. */
  _fakePartial() {
    this.emit('partial', { text: '…', sessionId: this.sessionId });
  }

  async _flush(reason) {
    if (this._closed || this._buffers.length === 0) {
      this._closed = true;
      this._cleanup();
      return;
    }
    this._closed = true;
    this._cleanup();

    const audioMs = this._estAudioMs();
    if (audioMs < MIN_AUDIO_MS) {
      this.emit('final', { text: '', sessionId: this.sessionId, reason: 'too-short', ms: audioMs });
      return;
    }

    const pcm = Buffer.concat(this._buffers);
    let wavBytes;
    try {
      wavBytes = encodeWav(pcm, SAMPLE_RATE);
    } catch (err) {
      this.emit('error', new Error(`wav encode failed: ${err.message}`));
      return;
    }

    try {
      const t0 = Date.now();
      const text = await transcribe(wavBytes, this.apiKey);
      this.emit('final', {
        text,
        sessionId: this.sessionId,
        reason,
        ms: Date.now() - t0,
        audioMs,
      });
    } catch (err) {
      this.emit('error', err);
    }
  }

  /** Force a flush even mid-stream (e.g. session ending). */
  end() {
    if (!this._closed) this._flush('end');
  }

  _cleanup() {
    if (this._silenceTimer) clearTimeout(this._silenceTimer);
    if (this._maxTimer) clearTimeout(this._maxTimer);
    this._silenceTimer = null;
    this._maxTimer = null;
  }

  _estAudioMs() {
    // pcm16 mono @ 16kHz → 32 000 bytes/sec
    return Math.round((this._totalBytes / (SAMPLE_RATE * 2)) * 1000);
  }
}

function pcm16Rms(buf) {
  let sumSq = 0;
  let n = 0;
  for (let i = 0; i + 1 < buf.byteLength; i += 2) {
    const s = buf.readInt16LE(i);
    sumSq += s * s;
    n += 1;
  }
  if (n === 0) return 0;
  return Math.sqrt(sumSq / n);
}

function encodeWav(pcm, sampleRate) {
  // node-wav.encode wants Float32Array channels in [-1, 1].
  const samples = pcm.byteLength / 2;
  const f32 = new Float32Array(samples);
  for (let i = 0; i < samples; i += 1) {
    f32[i] = pcm.readInt16LE(i * 2) / 0x8000;
  }
  return wav.encode([f32], { sampleRate, float: false, bitDepth: 16 });
}

async function transcribe(wavBytes, apiKey) {
  const form = new FormData();
  form.append('file', new Blob([wavBytes], { type: 'audio/wav' }), 'utterance.wav');
  form.append('model', 'gpt-4o-mini-transcribe');
  form.append('response_format', 'json');

  const res = await fetch('https://api.openai.com/v1/audio/transcriptions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}` },
    body: form,
  });
  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(`STT HTTP ${res.status}: ${errText.slice(0, 200)}`);
  }
  const data = await res.json();
  return (data.text ?? '').trim();
}
