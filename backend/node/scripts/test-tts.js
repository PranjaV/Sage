// B1 — Verify ElevenLabs Flash v2.5 + Sage voice clone.
// Streams TTS to out/test-tts.mp3, prints first-byte latency + bytes.

import { config } from 'dotenv';
import { mkdir, writeFile } from 'node:fs/promises';
import { createWriteStream } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, '..', '..', '..');
config({ path: resolve(repoRoot, '.env') });

const TEXT = 'Hello. I am Sage. I am here to help.';
// Default Rachel voice — ElevenLabs public default. B1 acceptance requires
// the Sage clone, so this fallback only proves the API works.
const FALLBACK_VOICE_ID = '21m00Tcm4TlvDq8ikWAM';

const apiKey = process.env.ELEVENLABS_API_KEY;
const voiceId = process.env.ELEVENLABS_VOICE_ID || FALLBACK_VOICE_ID;
const usingFallback = !process.env.ELEVENLABS_VOICE_ID;

if (!apiKey) {
  console.error('✗ ELEVENLABS_API_KEY missing in .env');
  process.exit(1);
}
if (usingFallback) {
  console.warn('⚠ ELEVENLABS_VOICE_ID not set — using default Rachel voice. The Sage voice clone ID is required for B1 acceptance.');
}

const url = `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}/stream?optimize_streaming_latency=4&output_format=mp3_44100_128`;

const body = {
  text: TEXT,
  model_id: 'eleven_flash_v2_5',
  voice_settings: { stability: 0.5, similarity_boost: 0.75 },
};

const outDir = resolve(repoRoot, 'out');
await mkdir(outDir, { recursive: true });
const outPath = resolve(outDir, 'test-tts.mp3');

const t0 = performance.now();
const ctrl = new AbortController();
const timer = setTimeout(() => ctrl.abort(), 5000);

let res;
try {
  res = await fetch(url, {
    method: 'POST',
    headers: {
      'xi-api-key': apiKey,
      'Content-Type': 'application/json',
      'Accept': 'audio/mpeg',
    },
    body: JSON.stringify(body),
    signal: ctrl.signal,
  });
} catch (err) {
  clearTimeout(timer);
  console.error(`✗ request failed: ${err.message}`);
  process.exit(1);
}

if (!res.ok) {
  clearTimeout(timer);
  const errText = await res.text().catch(() => '<no body>');
  console.error(`✗ HTTP ${res.status}: ${errText}`);
  process.exit(1);
}

const reader = res.body.getReader();
let firstByteMs = null;
let totalBytes = 0;
const chunks = [];

while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  if (firstByteMs === null) firstByteMs = Math.round(performance.now() - t0);
  totalBytes += value.byteLength;
  chunks.push(value);
}
clearTimeout(timer);

await writeFile(outPath, Buffer.concat(chunks.map((c) => Buffer.from(c.buffer, c.byteOffset, c.byteLength))));

console.log(`✓ first-byte: ${firstByteMs}ms | total bytes: ${totalBytes}`);
console.log(`  saved: ${outPath}`);
if (usingFallback) {
  console.log('  (default Rachel voice used — supply ELEVENLABS_VOICE_ID for the Sage clone)');
}
