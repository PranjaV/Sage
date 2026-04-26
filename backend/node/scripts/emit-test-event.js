// B7 — Drives the orb + transcript pipeline as a Socket.IO CLIENT.
// Run after the bridge is up. The bridge re-broadcasts each event to other
// connected clients (the Electron app + listener), letting the frontend
// validate state transitions before any real STT/TTS plumbing exists.

import { io } from 'socket.io-client';

const URL = process.env.BRIDGE_URL || 'http://localhost:3001';
const TTS_URL = `${URL}/static/test-tts.mp3`;

const sequence = [
  { event: 'orb:state', payload: { state: 'listening' }, delay: 800 },
  { event: 'transcript:partial', payload: { text: 'I need a' }, delay: 600 },
  { event: 'transcript:partial', payload: { text: 'I need a weekly' }, delay: 600 },
  { event: 'transcript:final', payload: { text: 'I need a weekly pill organizer.' }, delay: 400 },
  { event: 'orb:state', payload: { state: 'thinking' }, delay: 1200 },
  { event: 'agent:trace', payload: { node: 'supervisor', text: 'route → browser_agent' }, delay: 300 },
  { event: 'agent:trace', payload: { node: 'browser_agent', text: 'opening amazon.com' }, delay: 1500 },
  { event: 'orb:state', payload: { state: 'speaking' }, delay: 200 },
  { event: 'tts:chunk', payload: { url: TTS_URL }, delay: 2000 },
  { event: 'orb:state', payload: { state: 'complete' }, delay: 0 },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const socket = io(URL, { transports: ['websocket', 'polling'], reconnection: false });

socket.on('connect', async () => {
  console.log(`[emit] connected ${socket.id}`);
  for (const step of sequence) {
    socket.emit(step.event, step.payload);
    console.log(`[emit] → ${step.event} ${JSON.stringify(step.payload)}`);
    if (step.delay) await sleep(step.delay);
  }
  // Give the server a beat to flush, then exit.
  await sleep(150);
  socket.close();
  process.exit(0);
});

socket.on('connect_error', (err) => {
  console.error(`[emit] connect_error: ${err.message}`);
  process.exit(1);
});

setTimeout(() => {
  console.error('[emit] timeout — could not finish sequence in 15s');
  process.exit(1);
}, 15_000);
