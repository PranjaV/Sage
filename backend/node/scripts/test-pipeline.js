// End-to-end Phase 2 smoke: feed a recorded WAV through the bridge as if
// the Electron client were streaming pcm16 audio:chunks, and assert we get
// a transcript:final, agent:trace events, and tts:chunk + tts:done.
//
// Requires the bridge AND the Python orchestrator to be running.
// Uses ffmpeg to decode fixtures/sample.mp3 → pcm16 mono 16kHz.

import { config } from 'dotenv';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { io } from 'socket.io-client';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, '..', '..', '..');
config({ path: resolve(repoRoot, '.env') });

const BRIDGE_URL = process.env.BRIDGE_URL || 'http://localhost:3001';
const SAMPLE_MP3 = resolve(__dirname, 'fixtures', 'sample.mp3');
const CHUNK_BYTES = 3200; // 100ms of pcm16 mono @ 16kHz

async function decodeToPcm() {
  const mp3 = await readFile(SAMPLE_MP3);
  return new Promise((res, rej) => {
    const ff = spawn('ffmpeg', ['-i', 'pipe:0', '-f', 's16le', '-ac', '1', '-ar', '16000', 'pipe:1'], {
      stdio: ['pipe', 'pipe', 'inherit'],
    });
    const out = [];
    ff.stdout.on('data', (c) => out.push(c));
    ff.on('error', rej);
    ff.on('close', (code) => (code === 0 ? res(Buffer.concat(out)) : rej(new Error(`ffmpeg exit ${code}`))));
    ff.stdin.end(mp3);
  });
}

const seen = { transcriptPartial: 0, transcriptFinal: null, traces: [], orbStates: [], ttsChunks: 0, ttsDone: null, sessionEnded: null };

async function main() {
  console.log('… decoding sample mp3 → pcm16 mono 16kHz');
  const pcm = await decodeToPcm();
  console.log(`  pcm bytes: ${pcm.byteLength} (~${Math.round(pcm.byteLength / 32)}ms)`);

  const sock = io(BRIDGE_URL, { transports: ['websocket'], reconnection: false });

  await new Promise((res, rej) => {
    sock.on('connect', res);
    sock.on('connect_error', rej);
  });
  console.log(`… connected ${sock.id}`);

  let sessionId = null;
  sock.on('session:started', ({ session_id }) => { sessionId = session_id; });
  sock.on('transcript:partial', (p) => { seen.transcriptPartial += 1; console.log('  → partial', p); });
  sock.on('transcript:final', (p) => { seen.transcriptFinal = p; console.log('  → final', p); });
  sock.on('agent:trace', (p) => { seen.traces.push(p); console.log('  → trace', p); });
  sock.on('orb:state', (p) => { seen.orbStates.push(p.state); console.log('  → orb', p.state); });
  sock.on('tts:chunk', () => { seen.ttsChunks += 1; });
  sock.on('tts:done', (p) => { seen.ttsDone = p; console.log('  → tts:done', p); });
  sock.on('session:ended', (p) => { seen.sessionEnded = p; console.log('  → session:ended', p); });

  sock.emit('session:start', { patient_id: 'p_eleanor' });
  await new Promise((res) => setTimeout(res, 250));

  console.log('… streaming audio chunks');
  for (let i = 0; i < pcm.byteLength; i += CHUNK_BYTES) {
    const chunk = pcm.subarray(i, Math.min(i + CHUNK_BYTES, pcm.byteLength));
    sock.emit('audio:chunk', chunk.toString('base64'));
    await new Promise((res) => setTimeout(res, 30));
  }
  // Append ~1s of silence to trigger the silence gate.
  const silence = Buffer.alloc(16_000 * 2, 0);
  for (let i = 0; i < silence.byteLength; i += CHUNK_BYTES) {
    const chunk = silence.subarray(i, Math.min(i + CHUNK_BYTES, silence.byteLength));
    sock.emit('audio:chunk', chunk.toString('base64'));
    await new Promise((res) => setTimeout(res, 30));
  }

  console.log('… waiting for pipeline to complete');
  const deadline = Date.now() + 50_000;
  while (Date.now() < deadline && (!seen.transcriptFinal || !seen.ttsDone)) {
    await new Promise((res) => setTimeout(res, 250));
  }

  sock.emit('session:end');
  // Persistence does two Snowflake writes; wait up to 30s for confirmation.
  const endDeadline = Date.now() + 30_000;
  while (Date.now() < endDeadline && !seen.sessionEnded) {
    await new Promise((res) => setTimeout(res, 250));
  }
  await new Promise((res) => setTimeout(res, 100));
  sock.close();

  // ─── assertions ───
  const failures = [];
  if (!seen.transcriptFinal?.text?.toLowerCase().includes('pill organizer')) {
    failures.push(`transcript:final missing 'pill organizer' (got ${JSON.stringify(seen.transcriptFinal)})`);
  }
  if (!seen.orbStates.includes('thinking')) failures.push('no orb:state thinking');
  if (!seen.orbStates.includes('speaking')) failures.push('no orb:state speaking');
  if (!seen.orbStates.includes('complete')) failures.push('no orb:state complete');
  if (!seen.ttsDone) failures.push('no tts:done');
  if (seen.ttsChunks < 1) failures.push('no tts chunks');
  const supervisorTrace = seen.traces.find((t) => t.node === 'supervisor');
  if (!supervisorTrace) failures.push('no supervisor trace');
  if (!seen.sessionEnded) failures.push('no session:ended confirmation');
  else if (!seen.sessionEnded.persisted) failures.push('session:ended reports persisted=false');

  if (failures.length) {
    console.error('✗ pipeline failures:');
    for (const f of failures) console.error(`  - ${f}`);
    process.exit(1);
  }

  console.log(`✓ pipeline ok | transcript="${seen.transcriptFinal.text}" | orb=${seen.orbStates.join('→')} | tts=${seen.ttsChunks} chunks (${seen.ttsDone.engine}) | persisted=${seen.sessionEnded.persisted}`);
  process.exit(0);
}

main().catch((err) => {
  console.error(`✗ ${err?.message ?? err}`);
  process.exit(1);
});
