// ElevenLabs Flash v2.5 streaming TTS with OpenAI gpt-4o-mini-tts fallback.

const ELEVENLABS_VOICE_FALLBACK = '21m00Tcm4TlvDq8ikWAM'; // Rachel — only if no Sage clone

const ELEVEN_RATE_PER_CHAR = 0.000165; // Flash v2.5 list price reference

export const usage = {
  ttsChars: 0,
  ttsDollars: 0,
  fallbacksEngaged: 0,
};

/**
 * Stream TTS audio for `text`. Calls onChunk(buf) per network chunk, onDone({ ms, bytes, engine }) on completion.
 * Falls back to OpenAI gpt-4o-mini-tts if ElevenLabs errors. Caller is expected to keep `text` ≤100 words.
 */
export async function speak({ text, sessionId, onChunk, onDone }) {
  const trimmed = (text || '').trim();
  if (!trimmed) {
    onDone?.({ ms: 0, bytes: 0, chunks: 0, engine: 'noop' });
    return;
  }

  const startedAt = Date.now();
  console.log(`[tts] speak session=${sessionId ?? '-'} chars=${trimmed.length}`);

  try {
    const result = await speakElevenLabs({ text: trimmed, onChunk });
    const ms = Date.now() - startedAt;
    usage.ttsChars += trimmed.length;
    usage.ttsDollars += trimmed.length * ELEVEN_RATE_PER_CHAR;
    console.log(`[tts] ok engine=elevenlabs chunks=${result.chunks} ms=${ms} bytes=${result.bytes}`);
    onDone?.({ ms, bytes: result.bytes, chunks: result.chunks, engine: 'elevenlabs' });
    return;
  } catch (err) {
    console.warn(`[tts] elevenlabs failed (${err.message}) — engaging openai fallback`);
    usage.fallbacksEngaged += 1;
  }

  try {
    const result = await speakOpenAI({ text: trimmed, onChunk });
    const ms = Date.now() - startedAt;
    console.log(`[tts] ok engine=openai-fallback chunks=${result.chunks} ms=${ms} bytes=${result.bytes}`);
    onDone?.({ ms, bytes: result.bytes, chunks: result.chunks, engine: 'openai' });
  } catch (err) {
    console.error(`[tts] openai fallback also failed: ${err.message}`);
    onDone?.({ ms: Date.now() - startedAt, bytes: 0, chunks: 0, engine: 'failed', error: err.message });
  }
}

async function speakElevenLabs({ text, onChunk }) {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  if (!apiKey) throw new Error('ELEVENLABS_API_KEY missing');
  const voiceId = process.env.ELEVENLABS_VOICE_ID || ELEVENLABS_VOICE_FALLBACK;

  const url = `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}/stream?optimize_streaming_latency=4&output_format=mp3_44100_128`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'xi-api-key': apiKey,
      'Content-Type': 'application/json',
      Accept: 'audio/mpeg',
    },
    body: JSON.stringify({
      text,
      model_id: 'eleven_flash_v2_5',
      voice_settings: { stability: 0.5, similarity_boost: 0.75 },
    }),
  });
  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${errText.slice(0, 200)}`);
  }

  return drain(res.body, onChunk);
}

async function speakOpenAI({ text, onChunk }) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error('OPENAI_API_KEY missing');
  const res = await fetch('https://api.openai.com/v1/audio/speech', {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'gpt-4o-mini-tts',
      voice: 'alloy',
      input: text,
      response_format: 'mp3',
    }),
  });
  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${errText.slice(0, 200)}`);
  }
  return drain(res.body, onChunk);
}

async function drain(body, onChunk) {
  const reader = body.getReader();
  let chunks = 0;
  let bytes = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (!value || value.byteLength === 0) continue;
    const buf = Buffer.from(value.buffer, value.byteOffset, value.byteLength);
    chunks += 1;
    bytes += buf.byteLength;
    onChunk?.(buf);
  }
  return { chunks, bytes };
}
