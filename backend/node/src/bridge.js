// Sage bridge — Socket.IO + REST passthrough. Frontend's only entry point.
//
// Phase 1: health, hello, audio:chunk logging, heartbeat, re-broadcast.
// Phase 2:
//   - per-session StreamingSTT (B8) — audio:chunk → transcript:partial/final
//   - speak() integration (B9) — orb:state speaking → tts:chunk → tts:done
//   - /turn round-trip to Python orchestrator (with echo fallback if down)
//   - /internal/trace endpoint — Python pushes node traces, bridge re-emits
//   - /internal/browser-task endpoint — Python asks the bridge to run Stagehand
//   - session:start / session:end accumulate transcript for cognitive analysis

import { config } from 'dotenv';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import express from 'express';
import { Server as SocketIOServer } from 'socket.io';

import { StreamingSTT } from './stt.js';
import { speak, usage as ttsUsage } from './tts.js';
import { runBrowserTask, prewarm as prewarmStagehand } from './stagehand-runner.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, '..', '..', '..');
const outDir = resolve(repoRoot, 'out');
config({ path: resolve(repoRoot, '.env') });

const PORT = Number(process.env.BRIDGE_PORT || 3001);
const PY_BASE = process.env.PY_ORCHESTRATOR_URL || 'http://localhost:7777';

const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '4mb' }));

app.get('/health', (_req, res) => res.json({ ok: true }));
app.use('/static', express.static(outDir, { fallthrough: true, maxAge: 0 }));

const httpServer = createServer(app);
const io = new SocketIOServer(httpServer, {
  cors: { origin: '*', methods: ['GET', 'POST'] },
  maxHttpBufferSize: 8 * 1024 * 1024,
});

/** session_id → { socket, sttSession, interactions[], startedAt } */
const sessions = new Map();
/** internal "hops" we never re-broadcast even if some client emits them */
const HANDLED_EVENTS = new Set(['hello', 'audio:chunk', 'session:start', 'session:end']);

function emitToSession(_sessionId, event, payload) {
  // io.emit reaches every connected client (Electron orb + dashboard + listener).
  // Sessions are coarse for now; targeted rooms can be introduced if a second
  // patient ever joins simultaneously.
  io.emit(event, payload);
}

io.on('connection', (socket) => {
  console.log(`[bridge] socket connected id=${socket.id}`);

  socket.on('hello', () => socket.emit('hello', { ok: true, ts: Date.now() }));

  socket.on('session:start', (payload = {}) => {
    const patientId = payload.patient_id || 'p_eleanor';
    const sessionId = payload.session_id || `${patientId}:${randomUUID()}`;
    createSession(sessionId, socket, patientId);
    socket.data.sessionId = sessionId;
    socket.emit('session:started', { session_id: sessionId, patient_id: patientId });
    console.log(`[bridge] session:start ${sessionId}`);
  });

  socket.on('session:end', async () => {
    const sessionId = socket.data?.sessionId;
    if (!sessionId) return;
    const session = sessions.get(sessionId);
    if (!session) return;
    session.sttSession?.end();
    // Give any in-flight final transcript a beat to land before persisting.
    await new Promise((r) => setTimeout(r, 250));

    const startedAtIso = new Date(session.startedAt).toISOString();
    const endedAtIso = new Date().toISOString();
    let persisted = null;
    try {
      const r = await fetch(`${PY_BASE}/session/end`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          patient_id: session.patientId,
          started_at: startedAtIso,
          ended_at: endedAtIso,
          interactions: session.interactions,
          primary_task: session.primaryTask,
        }),
        signal: AbortSignal.timeout(15_000),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      persisted = await r.json();
    } catch (err) {
      console.error(`[bridge] session:end persistence failed: ${err.message}`);
    }

    socket.emit('session:ended', {
      session_id: sessionId,
      interactions: session.interactions.length,
      duration_seconds: Math.round((Date.now() - session.startedAt) / 1000),
      persisted: !!persisted,
      cognitive_analysis: persisted?.cognitive_analysis ?? { status: 'unavailable' },
    });
    console.log(`[bridge] session:end ${sessionId} (${session.interactions.length} interactions) persisted=${!!persisted}`);
    sessions.delete(sessionId);
  });

  socket.on('audio:chunk', (b64) => {
    const sessionId = socket.data?.sessionId;
    if (!sessionId) return;
    const session = sessions.get(sessionId);
    if (!session) return;

    const buf = Buffer.isBuffer(b64) ? b64 : Buffer.from(typeof b64 === 'string' ? b64 : '', 'base64');
    if (buf.byteLength === 0) return;
    session.sttSession.push(buf);
  });

  socket.onAny((event, payload) => {
    if (HANDLED_EVENTS.has(event)) return;
    if (event.startsWith('tts:') || event.startsWith('orb:') || event.startsWith('agent:') || event.startsWith('transcript:') || event === 'session:started' || event === 'session:ended') {
      // Outgoing events reflected by tools/listeners — pass through to peers.
      socket.broadcast.emit(event, payload);
      return;
    }
    const preview = payload && typeof payload === 'object' ? JSON.stringify(payload).slice(0, 120) : String(payload ?? '');
    console.log(`[bridge] ← ${event} ${preview}`);
    socket.broadcast.emit(event, payload);
  });

  socket.on('disconnect', (reason) => {
    const sessionId = socket.data?.sessionId;
    if (sessionId) sessions.delete(sessionId);
    console.log(`[bridge] socket disconnected id=${socket.id} reason=${reason}`);
  });
});

function createSession(sessionId, socket, patientId) {
  const stt = new StreamingSTT({ sessionId });
  const session = {
    socket,
    patientId: patientId || sessionId.split(':', 1)[0],
    sttSession: stt,
    interactions: [],
    startedAt: Date.now(),
    primaryTask: null,
  };
  sessions.set(sessionId, session);

  stt.on('partial', ({ text }) => {
    if (text) emitToSession(sessionId, 'transcript:partial', { text, session_id: sessionId });
  });

  stt.on('final', async ({ text }) => {
    if (!text) return;
    emitToSession(sessionId, 'transcript:final', { text, session_id: sessionId });
    session.interactions.push({ speaker: 'patient', utterance: text, ts: new Date().toISOString() });
    await handleUtterance(sessionId, text);
  });

  stt.on('error', (err) => {
    console.error(`[bridge:stt] ${err.message}`);
    emitToSession(sessionId, 'agent:trace', { node: 'stt', text: `error: ${err.message}` });
  });

  return session;
}

async function handleUtterance(sessionId, text) {
  emitToSession(sessionId, 'orb:state', { state: 'thinking' });

  let responseText;
  let trace = [];
  let intent = null;
  let payloadGoal = null;
  try {
    const r = await fetch(`${PY_BASE}/turn`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, text }),
      signal: AbortSignal.timeout(40_000),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    responseText = data.response_text;
    trace = data.trace ?? [];
    intent = data.intent ?? null;
    payloadGoal = data.payload_goal ?? null;
  } catch (err) {
    console.warn(`[bridge] /turn unavailable (${err.message}) — using echo fallback`);
    responseText = `I heard you say ${text}`;
  }

  // Trace events are already streamed live by Python via /internal/trace —
  // the `trace` field on the response is for logging/diagnostics only.
  void trace;

  const session = sessions.get(sessionId);
  if (session) {
    session.interactions.push({ speaker: 'sage', utterance: responseText, ts: new Date().toISOString() });
    // First substantive intent wins for primary_task — browser tasks have priority.
    if (intent === 'browser_task' && payloadGoal) {
      session.primaryTask = `browser: ${payloadGoal}`;
    } else if (!session.primaryTask && intent && intent !== 'smalltalk') {
      session.primaryTask = intent;
    }
  }

  emitToSession(sessionId, 'orb:state', { state: 'speaking' });
  await speak({
    text: responseText,
    sessionId,
    onChunk: (buf) => emitToSession(sessionId, 'tts:chunk', { b64: buf.toString('base64') }),
    onFallback: (reason) => emitToSession(sessionId, 'tts:fallback-engaged', { reason }),
    onDone: ({ ms, bytes, engine }) => {
      emitToSession(sessionId, 'tts:done', { ms, bytes, engine });
      emitToSession(sessionId, 'orb:state', { state: 'complete' });
    },
  });
}

// ─── REST endpoints reachable from the Python orchestrator ────────────────────

app.post('/internal/trace', (req, res) => {
  const { session_id, node, text } = req.body || {};
  if (!session_id || !node) return res.status(400).json({ ok: false, error: 'session_id+node required' });
  emitToSession(session_id, 'agent:trace', { node, text: text ?? '' });
  res.json({ ok: true });
});

app.post('/internal/analysis-ready', (req, res) => {
  const { session_id, score, severity } = req.body || {};
  if (!session_id) return res.status(400).json({ ok: false, error: 'session_id required' });
  console.log(`[cognitive] analysis ready session=${session_id} score=${score} severity=${severity}`);
  // Broadcast — caregiver dashboard listens on a separate socket and reloads.
  io.emit('cognitive:ready', { session_id, score, severity });
  res.json({ ok: true });
});

app.post('/internal/session-cost', (req, res) => {
  const { session_id, in: inTok = 0, out: outTok = 0, dollars = 0 } = req.body || {};
  if (!session_id) return res.status(400).json({ ok: false, error: 'session_id required' });
  // Roll in TTS usage (the bridge owns ElevenLabs/OpenAI TTS).
  const ttsChars = ttsUsage.ttsChars;
  const ttsDollars = ttsUsage.ttsDollars;
  const total = Number(dollars) + ttsDollars;
  console.log(
    `Session ${session_id} cost: $${total.toFixed(4)} ` +
      `(LLM $${Number(dollars).toFixed(4)} in=${inTok} out=${outTok} | ` +
      `TTS $${ttsDollars.toFixed(4)} chars=${ttsChars})`,
  );
  io.emit('session:cost', {
    session_id,
    llm: { in: inTok, out: outTok, dollars: Number(dollars) },
    tts: { chars: ttsChars, dollars: ttsDollars },
    total_dollars: total,
  });
  res.json({ ok: true });
});

app.post('/internal/browser-task', async (req, res) => {
  const { goal, session_id } = req.body || {};
  if (!goal) return res.status(400).json({ ok: false, error: 'goal required' });
  try {
    const result = await runBrowserTask({
      goal,
      onTrace: (text) => session_id && emitToSession(session_id, 'agent:trace', { node: 'browser_agent', text }),
    });
    res.json({ ok: true, ...result });
  } catch (err) {
    console.error(`[bridge] browser-task error: ${err.message}`);
    res.status(200).json({ ok: false, reason: err.message });
  }
});

const heartbeatTimer = setInterval(() => {
  io.emit('heartbeat', { ts: Date.now() });
}, 1000);

httpServer.listen(PORT, () => {
  console.log(`bridge online :${PORT} (python orchestrator: ${PY_BASE})`);
  // Optional: STAGEHAND_PREWARM=0 disables. Default on so first call is fast.
  if (process.env.STAGEHAND_PREWARM !== '0') prewarmStagehand();
});

function shutdown(signal) {
  console.log(`[bridge] ${signal} received — shutting down`);
  clearInterval(heartbeatTimer);
  io.close(() => {
    httpServer.close(() => process.exit(0));
  });
  setTimeout(() => process.exit(0), 2000).unref();
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
