// Sage bridge — Socket.IO + REST passthrough. Frontend's only entry point.
// Phase 1 (B6+B7) scope: health, hello, audio:chunk logging, heartbeat,
// graceful shutdown, re-broadcast of any client event, static-serve out/.

import { config } from 'dotenv';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import express from 'express';
import { Server as SocketIOServer } from 'socket.io';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, '..', '..', '..');
const outDir = resolve(repoRoot, 'out');
config({ path: resolve(repoRoot, '.env') });

const PORT = Number(process.env.BRIDGE_PORT || 3001);

const app = express();
app.disable('x-powered-by');

app.get('/health', (_req, res) => res.json({ ok: true }));

// Static-serve out/ so the frontend can fetch the test mp3 etc.
app.use('/static', express.static(outDir, { fallthrough: true, maxAge: 0 }));

const httpServer = createServer(app);
const io = new SocketIOServer(httpServer, {
  cors: { origin: '*', methods: ['GET', 'POST'] },
  // Electron loads from file:// — open CORS is fine on a localhost-only bridge.
  maxHttpBufferSize: 8 * 1024 * 1024,
});

io.on('connection', (socket) => {
  console.log(`[bridge] socket connected id=${socket.id}`);

  socket.on('hello', () => {
    socket.emit('hello', { ok: true, ts: Date.now() });
  });

  socket.on('audio:chunk', (b64) => {
    const len = typeof b64 === 'string' ? Buffer.byteLength(b64, 'base64') : (b64?.byteLength ?? 0);
    console.log(`[bridge] audio chunk ${len} bytes`);
  });

  // Re-broadcast any client-emitted event to other connected clients.
  // Keeps the test emitter, Electron app, and dashboard in sync without a
  // dedicated event registry. Use socket.broadcast (NOT io.emit) so the
  // sender does not echo themselves.
  socket.onAny((event, payload) => {
    if (event === 'hello' || event === 'audio:chunk') return; // handled above
    const preview = payload && typeof payload === 'object' ? JSON.stringify(payload).slice(0, 120) : String(payload ?? '');
    console.log(`[bridge] ← ${event} ${preview}`);
    socket.broadcast.emit(event, payload);
  });

  socket.on('disconnect', (reason) => {
    console.log(`[bridge] socket disconnected id=${socket.id} reason=${reason}`);
  });
});

const heartbeatTimer = setInterval(() => {
  io.emit('heartbeat', { ts: Date.now() });
}, 1000);

httpServer.listen(PORT, () => {
  console.log(`bridge online :${PORT}`);
});

function shutdown(signal) {
  console.log(`[bridge] ${signal} received — shutting down`);
  clearInterval(heartbeatTimer);
  io.close(() => {
    httpServer.close(() => process.exit(0));
  });
  // Hard kill if a hanging socket holds us up.
  setTimeout(() => process.exit(0), 2000).unref();
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
