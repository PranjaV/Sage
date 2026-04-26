# Sage Working Context

Last updated: April 25, 2026

## What we are building

Sage is a voice-first accessibility assistant for older adults. In the hackathon build, it helps a patient complete a meaningful digital task and gives a caregiver a post-session cognitive-signal summary.

## Current scope

- Electron patient app with orb states
- voice input, STT, intent routing, TTS
- one primary live web task and one secondary support flow
- session transcript accumulation
- post-session cognitive analysis
- Next.js caregiver dashboard
- Snowflake-backed score, trends, transcript, and one Cortex Analyst query

## Current architecture decisions

- one live Electron client only
- caregiver dashboard is separate and shown after the live patient demo
- no real-time patient/dashboard sync in the hackathon build
- cognitive analysis runs async after the session ends
- Snowflake is the source of truth for sessions and caregiver views
- structured patient profile first; semantic memory later if time

## Product guardrails

- explicit consent, no hidden monitoring
- no medical diagnosis claims
- reliability over feature count
- calm and dignified UX

## Current model/tool direction

- STT: OpenAI `gpt-4o-mini-transcribe`
- routing: OpenAI `gpt-4.1-mini`
- browser execution: OpenAI `gpt-4.1`
- deterministic cognitive scoring first
- caregiver summary: OpenAI `gpt-5-mini`
- TTS: ElevenLabs `Flash v2.5` with custom Sage voice clone (75ms latency, Pro tier); fallback to OpenAI `gpt-4o-mini-tts` if ElevenLabs errors on stage
- automation: Stagehand
- analytics: Snowflake + Cortex Analyst

## Demo structure

Flow A:
- patient speaks
- Sage responds warmly
- web task executes
- Sage confirms completion

Flow B:
- caregiver dashboard shows latest score
- trend chart updates
- transcript highlights appear
- one natural-language analyst query runs

## Current priorities

1. stabilize voice loop
2. lock one reliable Amazon medical-supplies flow
3. get session logging and analysis into Snowflake
4. render caregiver dashboard from seeded plus fresh data
5. rehearse the 4-minute demo

## Biggest risks

- live third-party web automation failure
- audio format mismatch
- overclaiming clinical value
- too many moving parts for a hackathon
- uncontrolled API spend if prompts and retries get sloppy

## Source-of-truth files

- `C:\Users\karis\Downloads\sage_prd.md`
- `C:\Users\karis\Downloads\newbackendPRD.docx`
- `C:\Users\karis\OneDrive\Documents\New project\SAGE_FINAL_PRD.md`
- `SAGE_FINAL_PRD.md` (in repo root)

## Build plans (parallel two-engineer execution)

- `PLAN_A_BACKEND.md` — node bridge + python LangGraph + Snowflake + cognitive analysis
- `PLAN_B_FRONTEND.md` — Electron orb + Next.js caregiver dashboard

Three sync checkpoints:
- CP1 (~hour 4): backend emit-test-event drives the orb + transcript
- CP2 (~hour 10): full pipe — voice → STT → LangGraph → Stagehand → Snowflake → TTS → cognitive widget
- CP3 (~hour 20): dress rehearsal of the 4-minute demo

## Working rule

If a decision improves demo reliability, dignity, and clarity, prefer it over extra technical ambition.

## Backend layout

- node bridge: `localhost:3001` — Socket.IO + REST. Owns ElevenLabs TTS, OpenAI STT, Stagehand.
- python orchestrator: `localhost:7777` — FastAPI. Owns LangGraph, Snowflake, cognitive analysis.
- Frontend talks ONLY to the node bridge. Python is reachable only from the bridge over `localhost:7777`.

## Verified externals

- ElevenLabs Flash v2.5 + Sage voice clone (`PerZoH0r6nxBZXCoIPpv`) — verified 2026-04-25 — first-byte 383ms warm.
- Snowflake round-trip — verified 2026-04-25 (role `sage_backend_role`, db `sage_db.core`). Account locator in `.env`.
- Stagehand → Amazon search — verified 2026-04-25 on Browserbase (project `94181ee1-…`, gpt-4.1-mini). LOCAL Playwright Chromium also confirmed working as a fallback.
- OpenAI gpt-4o-mini-transcribe — verified 2026-04-25 — round-trip 1524ms on a ~35KB mp3.

## Known caveats from Phase 0

- OpenAI org is on a 30k TPM limit for gpt-4.1; Stagehand's full-DOM extract exceeds this. Verification uses gpt-4.1-mini. Before B11 ships in production, either raise the org tier or scope the DOM passed to `extract`.

## Build log

After every completed task in PLAN_A or PLAN_B, append a single line here with the date and what is now working. This is how the other engineer stays oriented without a standup.

<!-- format: - YYYY-MM-DD HH:MM | A|B | <one line> -->
- 2026-04-25 17:30 | A | Phase 0 risk gauntlet passed — B1 ElevenLabs TTS, B2 Snowflake, B3 Stagehand→Amazon (LOCAL), B4 OpenAI STT all green.
- 2026-04-25 17:55 | A | Sage voice clone wired (PerZoH0r6nxBZXCoIPpv, 383ms first-byte) + new Browserbase key verified (Stagehand on Browserbase ok).
- 2026-04-25 18:05 | A | B5 canonical layout scaffolded — backend/node/{src,scripts}, backend/py/{src/sage/{nodes,…},scripts}, pyproject.toml, .env/.env.example/.gitignore.
- 2026-04-25 18:10 | A | B6 bridge online :3001 — Socket.IO + GET /health + heartbeat 1s + audio:chunk logging + graceful SIGINT/SIGTERM.
- 2026-04-25 18:15 | A | B7 emit-test-event wired — bridge re-broadcasts client events (socket.broadcast.emit), /static serves out/test-tts.mp3 (200, 41422 bytes), full 10-event sequence flowed through end-to-end. Ready for CHECKPOINT 1.

