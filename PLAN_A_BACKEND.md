# PLAN A — BACKEND ENGINEER

**Owner:** Backend
**Total budget:** ~20 hours
**Goal at hour 20:** Voice → STT → LangGraph → Stagehand → Snowflake → ElevenLabs round-trips reliably; Cortex Analyst answers caregiver questions.

---

## Read this first (5 min)

You are building the backend half of Sage. Your counterpart is building Electron + Next.js dashboard. You only sync at three checkpoints. Do **not** wait on them between checkpoints.

**Your stack:**
- Node.js (Socket.IO bridge, ElevenLabs, Stagehand wrapper) — `backend/node`
- Python (LangGraph orchestrator, Snowflake writes, cognitive scoring) — `backend/py`
- The two halves talk over a local FastAPI HTTP boundary on `localhost:7777`

**Why split:** LangGraph's best Python ergonomics + Stagehand's first-class Node SDK. Don't fight it.

**Working rule:** After every task ✓ completes, append a one-liner to `CLAUDE.md` under `## Build log` with timestamp + what's now working. This is how the frontend engineer stays oriented when you're not in the same room.

---

## Phase 0 — RISK GAUNTLET (Hours 0–2) [DO NOT SKIP, DO NOT REORDER]

If any of B1–B4 fails, **stop and fix before proceeding**. These are the four ways the demo dies. Find out now.

---

### B1 — Verify ElevenLabs Flash v2.5 + Sage voice clone  `[P0] [20m]`

**Prompt for Claude Code:**
```
Skills: voice-ai-engine-development

Scaffold a new directory `backend/node` with `package.json` (type: module) and create `backend/node/scripts/test-tts.js`.

The script must:
1. Load `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` from a `.env` at repo root using `dotenv`.
2. Call ElevenLabs Flash v2.5 streaming endpoint with the text:
   "Hello. I am Sage. I am here to help."
3. Use model_id `eleven_flash_v2_5`, output_format `mp3_44100_128`,
   voice_settings { stability: 0.5, similarity_boost: 0.75 },
   optimize_streaming_latency: 4.
4. Measure time-to-first-byte (ms) and total bytes received.
5. Pipe the stream to `out/test-tts.mp3` (mkdir if missing).
6. Print: `✓ first-byte: <ms> | total bytes: <n>` on success, exit 1 on failure within 5s.

Use the official `@elevenlabs/elevenlabs-js` SDK if it supports streaming; otherwise raw `fetch` to `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream`.

Then install deps and run: `node backend/node/scripts/test-tts.js`.

After it succeeds, append to CLAUDE.md under a new heading `## Verified externals`:
`- ElevenLabs Flash v2.5 + Sage voice clone — verified <ISO date> — first-byte <ms>`
```

**Acceptance test (60s):**
1. `node backend/node/scripts/test-tts.js`
2. Console prints `✓ first-byte: <X> | total bytes: <Y>` with X under 400ms.
3. Open `out/test-tts.mp3` — you must hear **the Sage voice clone** (not the default ElevenLabs voice) say the exact line. If the voice sounds generic, the voice ID is wrong.

**If it fails:**
- `401 Unauthorized` → regenerate `ELEVENLABS_API_KEY` at elevenlabs.io → API Keys.
- `voice_not_found` → grab voice ID from elevenlabs.io → Voices → your Sage clone → ⓘ.
- First-byte > 1s → check you actually used the streaming endpoint and `optimize_streaming_latency: 4`. Non-streaming will not survive the demo.

---

### B2 — Verify Snowflake connection + write + read  `[P0] [25m]`

**Prompt for Claude Code:**
```
Skills: snowflake-development

Create `backend/py/scripts/test_snowflake.py` and a `backend/py/pyproject.toml` (or `requirements.txt` if you prefer pip). Use `snowflake-connector-python` with `snowflake-snowpark-python` available for later.

Load from `.env` at repo root:
SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD,
SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA, SNOWFLAKE_ROLE.

The script must:
1. Connect.
2. CREATE TABLE IF NOT EXISTS sage_smoke_test (id INT, note STRING, ts TIMESTAMP_NTZ).
3. INSERT one row with id=1, note='hello sage', ts=CURRENT_TIMESTAMP.
4. SELECT it back and print the row.
5. DROP the table.
6. Print `✓ Snowflake round-trip ok` on success, traceback + exit 1 on failure.

Run with `python backend/py/scripts/test_snowflake.py`. After success append to CLAUDE.md under `## Verified externals`:
`- Snowflake round-trip — verified <ISO date>`
```

**Acceptance test (60s):**
1. `python backend/py/scripts/test_snowflake.py`
2. Console shows the inserted row + `✓ Snowflake round-trip ok`.
3. No leftover `sage_smoke_test` table when you check via Snowsight.

**If it fails:**
- `250001 Could not connect` → account locator wrong. Use the locator from the URL, e.g. `xy12345.us-east-1`.
- `Authentication failed` → check `SNOWFLAKE_PASSWORD` (no quotes in `.env`).
- `Object does not exist` → role/warehouse/database/schema not granted. Run `USE ROLE`, `USE WAREHOUSE`, etc. in Snowsight first to confirm they exist.

---

### B3 — Verify Stagehand opens Amazon and finds a product  `[P0] [25m]`

**Prompt for Claude Code:**
```
Skills: browser-automation, voice-ai-engine-development

In `backend/node`, install `@browserbasehq/stagehand` and `playwright`. Create `backend/node/scripts/test-stagehand.js`.

The script must:
1. Load BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID, OPENAI_API_KEY from `.env`.
2. Construct a Stagehand instance with env "BROWSERBASE" if BROWSERBASE_API_KEY is set, else "LOCAL". Use modelName "gpt-4.1".
3. Navigate to https://www.amazon.com.
4. Use stagehand.act("search for 'weekly pill organizer 7 day'").
5. Use stagehand.extract({ instruction: "extract the title and price of the first product card", schema: zod with title:string, price:string }).
6. Print the extracted product, then close.
7. Save a screenshot to out/test-stagehand.png.
8. Hard timeout: 30s total. Exit 1 on timeout, print `✓ Stagehand ok | <title> | <price>` on success.

Run with `node backend/node/scripts/test-stagehand.js`.

Append to CLAUDE.md `## Verified externals`:
`- Stagehand → Amazon search — verified <ISO date>`
```

**Acceptance test (60s):**
1. `node backend/node/scripts/test-stagehand.js`
2. Console prints `✓ Stagehand ok | <some product title> | $<price>` within 30s.
3. `out/test-stagehand.png` shows Amazon results page.

**If it fails:**
- `Browserbase auth` → wrong key/project. If you don't have Browserbase, set env to LOCAL and let Playwright launch local Chromium.
- `act() timeout` → Amazon hit a CAPTCHA. Switch to LOCAL mode and run with `headless: false` to see what's happening; log into amazon.com once in the launched browser, then it will be remembered if you set `userDataDir`.
- `extract returned null` → tighten the instruction to "the first product result with a price visible".

---

### B4 — Verify OpenAI gpt-4o-mini-transcribe  `[P0] [15m]`

**Prompt for Claude Code:**
```
Skills: voice-ai-development

Create `backend/node/scripts/test-stt.js`.

1. Load OPENAI_API_KEY from `.env`.
2. Read a sample WAV from `backend/node/scripts/fixtures/sample.wav`. If it doesn't exist, create one by calling ElevenLabs (reuse logic from B1) to synthesize "I need a weekly pill organizer please" and save as a 16kHz mono WAV (use ffmpeg or `wav` package — actually save mp3 then convert; if conversion is hard, save as mp3 and pass to OpenAI directly, the API accepts mp3).
3. POST the file to https://api.openai.com/v1/audio/transcriptions with model `gpt-4o-mini-transcribe`, response_format `json`.
4. Print `✓ STT: "<transcript>"` on success. Exit 1 on failure.

Run with `node backend/node/scripts/test-stt.js`.

Append to CLAUDE.md `## Verified externals`:
`- OpenAI gpt-4o-mini-transcribe — verified <ISO date>`
```

**Acceptance test (60s):**
1. `node backend/node/scripts/test-stt.js`
2. Console prints `✓ STT: "I need a weekly pill organizer please"` (close enough — punctuation may vary).

**If it fails:**
- `Invalid file format` → ensure mono 16kHz or just use mp3 — OpenAI accepts both.
- `model_not_found` → confirm spelling `gpt-4o-mini-transcribe` exactly (note: not `gpt-4o-transcribe`).

---

## Phase 1 — FOUNDATION (Hours 2–4)

### B5 — Project skeleton and `.env`  `[P0] [20m]`

**Prompt for Claude Code:**
```
Create the canonical layout:

backend/
  node/
    package.json (type: module, scripts: dev, start)
    src/
      bridge.js          # Socket.IO server + REST passthrough to Python
      tts.js             # ElevenLabs streaming wrapper
      stt.js             # OpenAI STT wrapper
      stagehand-runner.js  # subprocess-friendly Stagehand executor
    scripts/             # the four test-*.js from B1-B4 already here
  py/
    pyproject.toml
    src/sage/
      __init__.py
      app.py             # FastAPI on localhost:7777
      graph.py           # LangGraph supervisor
      nodes/
        supervisor.py
        browser_agent.py
        memory.py
        cognitive.py
      snowflake_io.py
      models.py          # pydantic schemas
    scripts/

Create `.env.example` listing every key with a comment. Do NOT commit `.env`. Add `.gitignore` covering `.env`, `out/`, `node_modules`, `__pycache__`, `*.mp3`, `*.png`.

Append to CLAUDE.md a new section:
## Backend layout
- node bridge: localhost:3001 (Socket.IO + REST)
- python orchestrator: localhost:7777 (FastAPI)
- Frontend talks ONLY to the node bridge.
```

**Acceptance test (60s):**
1. `tree backend -L 3` (or `Get-ChildItem -Recurse backend -Depth 2`) shows the structure above.
2. `.env.example` has every variable from B1–B4 listed.

**If it fails:** N/A — pure scaffolding.

---

### B6 — Socket.IO bridge skeleton with health  `[P0] [30m]`

**Prompt for Claude Code:**
```
In backend/node/src/bridge.js, build a Socket.IO server on port 3001 with:

- `socket.on('hello')` → emits back `{ ok: true, ts: Date.now() }`.
- `socket.on('audio:chunk', (b64))` → for now, just logs `audio chunk N bytes`.
- A periodic emit every 1s of `heartbeat` with payload `{ ts }`.
- CORS open (frontend is Electron, but it loads from file://).
- An HTTP route `GET /health` that returns `{ ok: true }`.
- Graceful shutdown on SIGINT.

Add a script `npm run dev` that runs with `--watch`. Confirm it boots on 3001.

Append to CLAUDE.md `## Build log`: `- bridge online :3001`.
```

**Acceptance test (60s):**
1. `npm --prefix backend/node run dev` — server prints `bridge online :3001`.
2. `curl http://localhost:3001/health` returns `{"ok":true}`.

**If it fails:** Port 3001 in use → `lsof -iTCP:3001` (or `netstat -ano | findstr 3001` on Windows) and kill the offender.

---

### B7 — Test event emitter (CHECKPOINT 1 prep)  `[P0] [15m]`

**Prompt for Claude Code:**
```
Create backend/node/scripts/emit-test-event.js that connects as a Socket.IO CLIENT to localhost:3001 and emits a sequence the frontend will use to validate the orb + transcript:

  orb:state { state: 'listening' }            (then 800ms)
  transcript:partial { text: 'I need a' }     (then 600ms)
  transcript:partial { text: 'I need a weekly' }       (then 600ms)
  transcript:final   { text: 'I need a weekly pill organizer.' }  (then 400ms)
  orb:state { state: 'thinking' }             (then 1200ms)
  agent:trace { node: 'supervisor', text: 'route → browser_agent' }  (300ms)
  agent:trace { node: 'browser_agent', text: 'opening amazon.com' }  (1500ms)
  orb:state { state: 'speaking' }             (then 200ms)
  tts:chunk { url: 'http://localhost:3001/static/test-tts.mp3' }     (then 2000ms)
  orb:state { state: 'complete' }
  exit

Update bridge.js so that any event a CLIENT emits gets re-broadcast to all OTHER clients. (Simple: socket.onAny((ev, payload) => socket.broadcast.emit(ev, payload))).

Static-serve out/test-tts.mp3 at /static/test-tts.mp3 so the frontend can play it.

Run: node backend/node/scripts/emit-test-event.js after bridge is up.
```

**Acceptance test (60s):**
1. Start bridge in one terminal.
2. `node backend/node/scripts/emit-test-event.js` in another.
3. Bridge logs show all events flowing through.

**If it fails:** Re-broadcast not working → ensure you used `socket.broadcast.emit`, not `io.emit` (which echoes back).

---

# 🟡 CHECKPOINT 1 (~hour 4)

**Both engineers stop. Test together.**

1. Backend: `npm --prefix backend/node run dev`
2. Frontend: starts Electron app
3. Frontend confirms socket connected (status pill green)
4. Backend: `node backend/node/scripts/emit-test-event.js`
5. Frontend orb cycles through states; transcript fills in word by word; agent trace appears; voice clip plays; orb returns to idle.

If this works, both engineers proceed independently. If not, fix here.

---

## Phase 2 — VOICE LOOP + INTENT (Hours 4–8)

### B8 — Audio chunk → STT pipeline  `[P0] [30m]`

**Prompt for Claude Code:**
```
In backend/node/src/stt.js, expose a class StreamingSTT that:
- Accepts pcm16 mono 16kHz chunks via .push(buf).
- Buffers until either silence detected (simple RMS gate, 700ms below threshold) OR 8s elapsed since first chunk.
- On flush, posts the WAV blob to gpt-4o-mini-transcribe.
- Emits 'partial' (after 1.5s of audio, naive midpoint) and 'final' transcripts.

Wire into bridge.js: when a client emits 'audio:chunk', append to the active StreamingSTT for that socket. On 'final', emit transcript:final and forward to Python orchestrator at POST localhost:7777/turn { session_id, text }.

For now stub the orchestrator response: if Python not up, fall back to a local echo "I heard you say <text>" and continue.
```

**Acceptance test (60s):**
1. Speak into the test page from CP1 saying "I need a pill organizer" (or use a pre-recorded chunked playback).
2. Console shows `transcript:final I need a pill organizer`.
3. Frontend transcript rail shows the text.

**If it fails:**
- Garbled transcript → wrong sample rate. Re-confirm 16kHz mono pcm16.
- API rejects → wrong WAV header. Use `node-wav` to write the header correctly.

---

### B9 — TTS streaming pipeline  `[P0] [30m]`

**Prompt for Claude Code:**
```
In backend/node/src/tts.js, export speak({ text, sessionId, onChunk, onDone }) that:
- Streams ElevenLabs Flash v2.5 (re-use settings from B1).
- For each chunk, calls onChunk(buffer).
- On end, calls onDone({ ms: total, bytes }).
- On error, falls back to OpenAI gpt-4o-mini-tts with voice 'alloy', text identical, and emits a single `tts:fallback-engaged` log.

Wire into bridge.js: when Python orchestrator returns a final response text, the bridge calls speak(...) and emits to the socket:
  orb:state { state: 'speaking' }
  tts:chunk { b64 }   (per chunk)
  tts:done  { ms }
  orb:state { state: 'complete' }

Keep responses ≤ 100 words. Log token-equivalent character count on every speak() call.
```

**Acceptance test (60s):**
1. Trigger a fake orchestrator response of "I found the pill organizer you usually order. I will place it now."
2. You hear the Sage voice over the speakers within 400ms of the trigger.
3. Console logs `[tts] 12 chunks, 2.1s, 87 chars`.

**If it fails:**
- Audio playback choppy on the frontend → that's a frontend buffering issue, not yours. Verify the backend is sending mp3 chunks ≥4KB. Smaller chunks make playback hiccup.

---

### B10 — LangGraph supervisor node  `[P0] [30m]`

**Prompt for Claude Code:**
```
Skills: langgraph

In backend/py/src/sage/graph.py build a LangGraph StateGraph with these nodes wired up:

State: { session_id, user_text, intent, response_text, browser_result, profile, trace[] }

Nodes:
- supervisor: gpt-4.1-mini, prompt: "Classify intent into one of: browser_task, memory_lookup, smalltalk, end_session. Return JSON {intent, reason}." Add to trace.
- memory_lookup: returns profile fields by query (calls snowflake_io.get_profile). Add to trace.
- browser_agent: stub for now — returns { ok: true, summary: "stubbed browser result" }. Add to trace.
- responder: gpt-4.1-mini, takes user_text + intent + memory_result + browser_result and produces a warm <100 word reply in the Sage voice (calm, dignified, never robotic). Add to trace.

Routing:
  START → supervisor
  supervisor → memory_lookup | browser_agent | responder (smalltalk goes direct to responder)
  memory_lookup → responder
  browser_agent → responder
  responder → END

Expose POST /turn at FastAPI in app.py:
  Input: { session_id, text }
  Output: { response_text, trace: [...] }

Stream trace events to bridge: each node, after running, POSTs to localhost:3001/internal/trace { session_id, node, text }. Bridge re-emits as agent:trace.

Run: uvicorn sage.app:app --port 7777 --reload

Append to CLAUDE.md ## Build log: `- langgraph supervisor live :7777`.
```

**Acceptance test (60s):**
1. Python orchestrator running on 7777.
2. `curl -X POST localhost:7777/turn -d '{"session_id":"t1","text":"how are you"}' -H "Content-Type: application/json"` returns `{response_text: "...", trace: [...]}` with at least supervisor + responder steps.
3. Bridge logs show agent:trace events being forwarded.

**If it fails:**
- Supervisor returns malformed JSON → use `response_format={"type":"json_object"}` on the OpenAI call.
- LangGraph version mismatch → pin `langgraph>=0.2`.

---

### B11 — Browser agent node (Stagehand wrapped)  `[P0] [45m]`

**Prompt for Claude Code:**
```
Skills: browser-automation

The browser agent lives in Node (Stagehand) but is called from Python. Pattern: Python posts to bridge POST /internal/browser-task { goal }, bridge runs Stagehand, returns result.

Node side (backend/node/src/stagehand-runner.js): export runBrowserTask({ goal }) that:
1. Boots Stagehand once (singleton, reuse across calls).
2. Navigates amazon.com if not already there.
3. stagehand.act(`Find a product matching: ${goal}. Click the first reasonable result.`)
4. stagehand.extract for { title, price }.
5. Returns { ok, title, price, screenshot_url } where screenshot_url is /static/<uuid>.png served by bridge.
6. Hard timeout 30s. On timeout, return { ok: false, reason: 'timeout' }. NEVER retry more than once.

Bridge: add POST /internal/browser-task that calls runBrowserTask and responds with the result. Also during execution, emit agent:trace events to the live socket: 'opening amazon', 'searching: <goal>', 'found: <title>'.

Python side: replace the browser_agent stub in graph.py with an httpx POST to localhost:3001/internal/browser-task.

Then in graph.py supervisor prompt, include in the routing example:
  "user: I need a pill organizer" → intent: browser_task, payload.goal: "weekly pill organizer 7 day"

The supervisor must extract the goal phrase from the user text into state.payload.goal so browser_agent gets a clean query.
```

**Acceptance test (60s):**
1. Bridge + python both running.
2. `curl -X POST localhost:7777/turn -d '{"session_id":"t2","text":"I need a weekly pill organizer"}' -H "Content-Type: application/json"`
3. Within 30s response includes `response_text` mentioning "pill organizer" + a price; trace shows supervisor → browser_agent → responder.
4. Browser visible (or screenshot saved) shows Amazon product page.

**If it fails:**
- Stagehand "page closed" → singleton lifecycle bug. Detach Stagehand from request — keep one instance for the whole process.
- Amazon redirect to .com.mx → set `extraHTTPHeaders: { 'Accept-Language': 'en-US' }` and navigate to amazon.com/?language=en_US.

---

### B12 — Memory / patient profile  `[P0] [30m]`

**Prompt for Claude Code:**
```
In Snowflake, create the schema from the PRD §9. Generate `backend/py/scripts/migrate.sql`:

CREATE TABLE IF NOT EXISTS patients (
  patient_id STRING, name STRING, age INT, caregiver_name STRING,
  baseline_score INT, consent_status STRING
);
CREATE TABLE IF NOT EXISTS patient_profile (
  patient_id STRING, doctors VARIANT, appointments VARIANT,
  pharmacy VARIANT, address VARIANT, common_items VARIANT
);
CREATE TABLE IF NOT EXISTS sessions (
  session_id STRING, patient_id STRING, started_at TIMESTAMP_NTZ,
  ended_at TIMESTAMP_NTZ, transcript STRING, duration_seconds INT,
  primary_task STRING
);
CREATE TABLE IF NOT EXISTS interactions (
  interaction_id STRING, session_id STRING, speaker STRING,
  utterance STRING, created_at TIMESTAMP_NTZ
);
CREATE TABLE IF NOT EXISTS cognitive_analyses (
  analysis_id STRING, session_id STRING, patient_id STRING,
  overall_score INT, severity STRING, baseline_delta INT,
  metrics VARIANT, flagged_phrases VARIANT, summary STRING,
  analyzed_at TIMESTAMP_NTZ
);

Create backend/py/scripts/seed.py that inserts ONE demo patient:
  patient_id='p_eleanor', name='Eleanor Hayes', age=78,
  caregiver_name='Sarah Hayes', baseline_score=82, consent_status='active'

And a profile:
  doctors: [{ name: 'Dr. Mehta', specialty: 'cardiology', phone: '555-0102' }]
  appointments: [{ doctor: 'Dr. Mehta', when: 'Thursday 9:00am', address: '450 Maple Ave' }]
  pharmacy: { name: 'CVS Maple', address: '410 Maple Ave' }
  address: { street: '12 Oak Lane', city: 'Boston', state: 'MA' }
  common_items: ['weekly pill organizer 7 day', 'large-print calendar', 'magnifying reader']

In backend/py/src/sage/snowflake_io.py expose:
  get_profile(patient_id) -> dict
  write_session(session_id, patient_id, started_at, ended_at, transcript, primary_task)
  write_interactions(session_id, items: list[{speaker, utterance, ts}])
  write_analysis(analysis: dict)
  list_recent_sessions(patient_id, limit=30) -> list

Run migrate.sql then seed.py. Append to CLAUDE.md ## Build log: `- snowflake schema + seed eleanor`.
```

**Acceptance test (60s):**
1. `python backend/py/scripts/seed.py` exits cleanly.
2. Snowsight: `SELECT * FROM patient_profile WHERE patient_id='p_eleanor'` shows the row with all VARIANT fields populated.
3. From Python REPL: `from sage.snowflake_io import get_profile; print(get_profile('p_eleanor'))` returns the profile.

**If it fails:**
- VARIANT writes — wrap dicts with `json.dumps` and pass via `PARSE_JSON` in the SQL: `INSERT INTO patient_profile SELECT 'p_eleanor', PARSE_JSON(%s), ...`.

---

### B13 — Memory lookup wired into LangGraph  `[P0] [30m]`

**Prompt for Claude Code:**
```
Update graph.py memory_lookup node:
- Input: state.user_text, state.session_id (carries patient_id)
- Use gpt-4.1-mini with prompt: "Given user utterance and patient profile JSON, return JSON {match: <profile field path>, summary: <one sentence>}."
- E.g. "I need to get to Dr. Mehta on Thursday" → {match: "appointments[0]", summary: "Dr. Mehta, Thursday 9:00am, 450 Maple Ave"}
- Add summary to state.response_text input for responder.

Update supervisor: add intent 'memory_lookup' for utterances about doctors, appointments, addresses, pharmacy, things "I usually" do, etc. Include 2 few-shot examples.

Test with curl:
  text: "When do I need to see Dr. Mehta?"
  expect: response mentions "Thursday 9 a.m." and trace shows memory_lookup node.
```

**Acceptance test (60s):**
1. `curl -X POST localhost:7777/turn -d '{"session_id":"p_eleanor:s1","text":"When do I see Dr. Mehta?"}' -H "Content-Type: application/json"`
2. Response mentions Thursday and 9am. Trace includes `memory_lookup`. No browser_agent in trace.

**If it fails:**
- Profile not loading → confirm session_id format `<patient_id>:<session_id>` is parsed in app.py.

---

## Phase 3 — END-TO-END (Hours 8–10)

### B14 — Wire mic→STT→graph→TTS round-trip  `[P0] [45m]`

**Prompt for Claude Code:**
```
Glue layer in bridge.js:

When transcript:final fires:
  1. Emit orb:state thinking.
  2. POST localhost:7777/turn { session_id, text }.
  3. Stream agent:trace events (already wired in B10).
  4. On response, call tts.speak(response_text) which streams audio + state changes.
  5. Append both user utterance and assistant response to in-memory session buffer keyed by session_id.

Add a 'session:end' socket event that:
  - Calls snowflake_io.write_session + write_interactions with the buffer.
  - Triggers cognitive analysis (Phase 4 — for now, write a stub that just logs `cognitive analysis queued`).
  - Clears buffer.

Add an 'session:start' event that creates a new session_id of form `${patient_id}:${uuid}` and clears any prior buffer.

Append to CLAUDE.md ## Build log: `- end-to-end round trip wired`.
```

**Acceptance test (60s):**
1. From frontend test page (CP1 still works), trigger a real spoken or simulated turn: "I need a weekly pill organizer".
2. Within 35s: orb cycles listening → thinking → speaking → complete; transcript fills; trace shows supervisor → browser_agent → responder; voice plays "I found one for you…" with a price.
3. `session:end` event causes a row to appear in Snowflake `sessions` and 2 rows in `interactions`.

**If it fails:** Buffer empty at session:end → in-memory map keyed by socket.id, but session_id used different key. Use a consistent map keyed by session_id.

---

# 🟡 CHECKPOINT 2 (~hour 10)

**Both engineers stop. Run the demo cold.**

1. Patient says: "I need one of those weekly pill organizers."
2. Sage responds, Stagehand orders, Sage confirms.
3. Patient says: "I need to get to Dr. Mehta on Thursday morning."
4. Sage retrieves memory, confirms appointment.
5. `session:end` fires.
6. Snowflake has the session row + interactions.
7. Frontend cognitive widget updates with a placeholder score.

If this whole sequence works, you are on track. If not, **fix only**, no new features.

---

## Phase 4 — COGNITIVE ANALYSIS (Hours 10–15)

### B15 — Deterministic scoring engine  `[P0] [45m]`

**Prompt for Claude Code:**
```
Create backend/py/src/sage/cognitive_score.py.

Input: list[{speaker, utterance, ts}] (patient utterances only used for scoring).
Output: dict matching PRD §8 output shape.

Implement these signals over patient utterances:
1. lexical_diversity: type-token ratio over patient utterances combined.
2. repetition_count: count of patient utterances ≥80% Jaccard-similar to a prior patient utterance in same session.
3. hesitation_count: count of "uh", "um", "er", "...", "let me think" tokens.
4. topic_drift_count: rough heuristic — count of sentences that change verbs/subjects without conjunctions; gpt-5-mini fallback if heuristic returns ambiguous.
5. word_finding_phrases: detect circumlocution patterns like "the thing", "you know what", "the one that", "what's it called". Return spans for each.

Score formula:
  base = 100
  - 4 * repetition_count
  - 2 * hesitation_count
  - 5 * topic_drift_count
  - 6 * len(word_finding_phrases)
  + bonus: 5 if lexical_diversity > 0.65 else 0
  Clamp to [0, 100].

Severity mapping:
  ≥85 ok, 70-84 watch, 50-69 attention, <50 follow-up.

baseline_delta = score - patient.baseline_score (from patients table).

Return matches PRD §8 shape. Include flagged_phrases with exact span text from word_finding_phrases. Never invent flags; if a phrase doesn't appear verbatim, omit it.

Write a unit test backend/py/tests/test_cognitive_score.py with 3 golden transcripts:
  - normal: ~95 score
  - mild concern: ~75 score
  - clear concern: ~55 score
Assert each lands in the expected bucket.
```

**Acceptance test (60s):**
1. `python -m pytest backend/py/tests/test_cognitive_score.py` — all 3 pass.
2. Run on a real CP2 transcript — score is between 60–95 (not 0, not 100, not None).

**If it fails:**
- Lexical diversity comes back wildly low → tokenization splitting on punctuation; use `re.findall(r"\b[a-zA-Z']+\b", text)`.

---

### B16 — gpt-5-mini caregiver summary  `[P0] [30m]`

**Prompt for Claude Code:**
```
In backend/py/src/sage/nodes/cognitive.py, add a function generate_summary(transcript_text, metrics, flagged_phrases, patient_name) using gpt-5-mini.

Prompt template (system):
"You are writing a caregiver-facing summary of a session with <patient_name>. Be calm, non-clinical, factual. Never use diagnostic language. Length: 2–3 sentences max. End with one suggested gentle follow-up."

User content includes the JSON of metrics + flagged_phrases + a 600-character transcript excerpt.

Output JSON: { session_summary, suggested_exercises (list of 1–2 items) }.

Wire into the cognitive analysis pipeline (called from session:end):
1. cognitive_score(...)
2. generate_summary(...)
3. Compose final analysis dict per PRD §8 shape.
4. snowflake_io.write_analysis(analysis_dict).
5. POST to bridge /internal/analysis-ready { session_id, score, severity } so frontend cognitive widget can refresh.

Log token usage on every gpt-5-mini call.
```

**Acceptance test (60s):**
1. End a session via frontend.
2. Within 10s, `cognitive_analyses` table has a new row.
3. The `summary` field reads naturally — never says "diagnosis", "dementia", "impairment".
4. Bridge log shows `[cognitive] tokens=<n> score=<n> severity=<s>`.

**If it fails:**
- Summary says clinical things → tighten the system prompt with explicit "do not use words: diagnosis, impairment, decline, dementia, cognitive disorder".

---

### B17 — Cortex Analyst semantic model  `[P0] [45m]`

**Prompt for Claude Code:**
```
Skills: snowflake-development

Create backend/py/scripts/cortex_semantic.yaml describing the semantic model over sessions, cognitive_analyses, patient_profile. Follow Snowflake's semantic model spec (verified_queries, dimensions, measures, time_dimension).

Tables:
- cognitive_analyses (fact): measures = overall_score (avg), baseline_delta (avg), severity counts; time_dim = analyzed_at; dim = patient_id.
- sessions: dim = primary_task, started_at; measure = duration_seconds.

Add ≥3 verified_queries:
  Q1: "What was the average score this week vs last week for Eleanor?"
  Q2: "How many sessions in the last 30 days had severity 'attention' or worse?"
  Q3: "What changed in today's session compared to the last three?"

Upload semantic model to a Snowflake stage (use snowflake-cli or `PUT` via connector) at @SAGE_STAGE/cortex/semantic.yaml.

Create endpoint POST /caregiver/ask in app.py:
  Input: { question }
  Output: { sql, answer_text, rows }
  Calls Cortex Analyst REST endpoint with the semantic model URI, returns the generated SQL, executes, summarizes.

Append to CLAUDE.md ## Build log: `- cortex analyst online`.
```

**Acceptance test (60s):**
1. `curl -X POST localhost:7777/caregiver/ask -d '{"question":"What changed in today'"'"'s session compared to the last three?"}' -H "Content-Type: application/json"`
2. Response includes a SQL string, rows, and a 1–2 sentence answer.

**If it fails:**
- Cortex Analyst not enabled → enable on your Snowflake account (Snowsight → Admin → Features) before the demo. This is a real gate.
- Schema mismatch → confirm column names in YAML exactly match table.

---

### B18 — Seed historical sessions for trend chart  `[P0] [30m]`

**Prompt for Claude Code:**
```
Create backend/py/scripts/seed_history.py that inserts 30 days of realistic-looking sessions for p_eleanor:

For each day (today minus 30 to today minus 1):
- 1 session of duration 45–180s
- transcript: pick from a pool of 6 realistic patient transcripts (3 normal, 2 mild concern, 1 clear concern), with light variation
- run cognitive_score on it to compute real scores
- write_session, write_interactions, write_analysis
- scores should drift gently downward over the 30 days (baseline 82 → today ~76) with one outlier dip at day -5 (score 64) to make the chart interesting

Run once. Verify with: SELECT analyzed_at, overall_score, severity FROM cognitive_analyses WHERE patient_id='p_eleanor' ORDER BY analyzed_at.
```

**Acceptance test (60s):**
1. `python backend/py/scripts/seed_history.py` completes.
2. Snowsight: 30 rows in cognitive_analyses for Eleanor with monotonic-ish but realistic scores 64–88.

**If it fails:** Slow inserts → batch with `executemany` or use Snowpark `write_pandas`.

---

## Phase 5 — POLISH + DEMO (Hours 15–20)

### B19 — Caregiver dashboard REST API  `[P0] [30m]`

**Prompt for Claude Code:**
```
Add to FastAPI app.py:

GET /caregiver/overview?patient_id=p_eleanor
  → { patient: {...}, latest_session: {...}, latest_score: int, severity: str, baseline_delta: int }

GET /caregiver/trend?patient_id=p_eleanor&days=30
  → { points: [{ date, score, severity }] }

GET /caregiver/sessions?patient_id=p_eleanor&limit=10
  → { sessions: [{ session_id, started_at, duration, primary_task, score, severity }] }

GET /caregiver/transcript?session_id=...
  → { transcript: [...], flagged_phrases: [...] }

(POST /caregiver/ask already exists from B17.)

Enable CORS for localhost:3000 (Next.js dev server). Document each endpoint with a short docstring.
```

**Acceptance test (60s):**
1. `curl localhost:7777/caregiver/overview?patient_id=p_eleanor | jq` returns the latest session info.
2. `curl localhost:7777/caregiver/trend?patient_id=p_eleanor&days=30` returns 30 points.

**If it fails:** N/A — straightforward CRUD.

---

### B20 — Reliability hardening  `[P1] [30m]`

**Prompt for Claude Code:**
```
Add three safety nets for the demo:

1. TTS fallback (already in B9) — confirm it triggers on simulated 500.
2. Stagehand fallback: if browser_agent returns { ok: false } with reason 'timeout' or 'not_found', the responder must say: "I had trouble finding that on Amazon just now. I can save it to your list and try again later. Is that okay?" instead of crashing.
3. Snowflake write retry: wrap write_session and write_analysis in a 2-attempt retry with 500ms backoff. If both fail, log loudly to console and write a JSON file backup to out/failed-writes/<session_id>.json. Never crash the bridge.

Add a script backend/scripts/chaos.sh that for each fallback simulates the failure and confirms the demo still completes a story (you'll run this once at hour 18 before the dress rehearsal).
```

**Acceptance test (60s):**
1. Kill ElevenLabs (set bad API key in env, restart bridge) — TTS fallback engages, voice still plays.
2. Block amazon.com in /etc/hosts (or simulate via timeout 1s) — supervisor still produces a graceful response.
3. Set bad Snowflake password — session ends, JSON backup written to out/failed-writes/.

**If it fails:** Fallbacks throw instead of catching → wrap with try/except at the orchestrator level, not just the leaf call.

---

### B21 — Token + cost logging  `[P1] [20m]`

**Prompt for Claude Code:**
```
Create backend/py/src/sage/usage.py: a singleton that accumulates token counts and dollar estimates per model.

Wrap every OpenAI call (supervisor, responder, memory_lookup, cognitive summary) and log:
  [usage] model=gpt-4.1-mini in=120 out=85 $=0.0019 session=<id>

At session:end, print and POST to bridge a `session:cost` event with the totals.

Same for ElevenLabs (count chars × Flash v2.5 rate: $0.000165/char).
```

**Acceptance test (60s):**
1. Run a turn; bridge console shows usage logs after each LLM call.
2. After session:end, bridge prints something like `Session p_eleanor:abc cost: $0.043 (LLM $0.018 + TTS $0.025)`.

**If it fails:** N/A.

---

### B22 — Final dress rehearsal support  `[P0] [60m]`

**Prompt for Claude Code:**
```
Create backend/scripts/demo-up.sh (and demo-up.ps1 for Windows) that:
1. Starts Python orchestrator (uvicorn ... --port 7777) in background.
2. Starts Node bridge (npm run dev) in background.
3. Tails both logs to a single file out/demo.log.
4. Health-checks both endpoints. Exits non-zero if either fails to come up in 10s.

Create demo-down.sh that stops both cleanly.

Pre-fly checklist file backend/PREFLIGHT.md:
  [ ] All 4 verified externals still pass (re-run B1–B4)
  [ ] Eleanor's profile + 30 days of history present
  [ ] Cortex Analyst returns answer for the demo question
  [ ] One full e2e turn completes in under 30s
  [ ] Fallback still works with ElevenLabs key removed

Walk through the checklist live. Do NOT add features after this.

Append to CLAUDE.md ## Build log: `- DRESS REHEARSAL PASSED <ISO date>`.
```

**Acceptance test (60s):**
1. `bash backend/scripts/demo-up.sh` — both services healthy in <10s.
2. Run the full 4-minute demo script end-to-end. Stopwatch under 4:00.

**If it fails:** Stop, fix, **do not add features**.

---

# 🔴 CHECKPOINT 3 (~hour 20) — Dress rehearsal

The exact 4-minute demo script runs perfectly once. If it doesn't, no new features. Fix only.

---

## Always-running rules

- After every task: append a one-liner to CLAUDE.md under `## Build log`.
- Token budget audit at hour 6, 12, 18: if you've burned >$8 on dev, shorten test loops.
- Before every commit: re-run B1–B4. They take 90 seconds combined and protect you from silent regressions.
- If you change an env var, update `.env.example` in the same commit.
- gpt-4.1 only inside Stagehand. gpt-4.1-mini for routing/responder. gpt-5-mini only for cognitive summary. Anywhere else you reach for a bigger model, stop and ask why.
