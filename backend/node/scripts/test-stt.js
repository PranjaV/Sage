// B4 — Verify OpenAI gpt-4o-mini-transcribe.
// Synthesizes a sample via ElevenLabs if none exists, then transcribes.

import { config } from 'dotenv';
import { existsSync } from 'node:fs';
import { mkdir, readFile, writeFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, '..', '..', '..');
config({ path: resolve(repoRoot, '.env') });

const SAMPLE_TEXT = 'I need a weekly pill organizer please.';
const FALLBACK_VOICE_ID = '21m00Tcm4TlvDq8ikWAM';

const openaiKey = process.env.OPENAI_API_KEY;
const elevenKey = process.env.ELEVENLABS_API_KEY;
const voiceId = process.env.ELEVENLABS_VOICE_ID || FALLBACK_VOICE_ID;

if (!openaiKey) {
  console.error('✗ OPENAI_API_KEY missing in .env');
  process.exit(1);
}

const fixturesDir = resolve(__dirname, 'fixtures');
await mkdir(fixturesDir, { recursive: true });
const sampleMp3 = resolve(fixturesDir, 'sample.mp3');

if (!existsSync(sampleMp3)) {
  if (!elevenKey) {
    console.error('✗ no fixture and ELEVENLABS_API_KEY missing — cannot synthesize sample');
    process.exit(1);
  }
  console.log('… synthesizing sample.mp3 via ElevenLabs');
  const url = `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}?output_format=mp3_44100_128`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'xi-api-key': elevenKey,
      'Content-Type': 'application/json',
      'Accept': 'audio/mpeg',
    },
    body: JSON.stringify({
      text: SAMPLE_TEXT,
      model_id: 'eleven_flash_v2_5',
      voice_settings: { stability: 0.5, similarity_boost: 0.75 },
    }),
  });
  if (!res.ok) {
    console.error(`✗ ElevenLabs synthesis failed: HTTP ${res.status} ${await res.text().catch(() => '')}`);
    process.exit(1);
  }
  const buf = Buffer.from(await res.arrayBuffer());
  await writeFile(sampleMp3, buf);
}

const fileBytes = await readFile(sampleMp3);
const fileInfo = await stat(sampleMp3);
console.log(`… sample: ${sampleMp3} (${fileInfo.size} bytes)`);

const form = new FormData();
form.append('file', new Blob([fileBytes], { type: 'audio/mpeg' }), 'sample.mp3');
form.append('model', 'gpt-4o-mini-transcribe');
form.append('response_format', 'json');

const t0 = performance.now();
const res = await fetch('https://api.openai.com/v1/audio/transcriptions', {
  method: 'POST',
  headers: { Authorization: `Bearer ${openaiKey}` },
  body: form,
});

if (!res.ok) {
  console.error(`✗ HTTP ${res.status}: ${await res.text().catch(() => '')}`);
  process.exit(1);
}

const data = await res.json();
const ms = Math.round(performance.now() - t0);
console.log(`✓ STT: "${data.text?.trim()}" (${ms}ms)`);
