# Sage demo preflight

Run this checklist within the hour before the demo. Do **not** add features
after this point — the rule for the last 90 minutes is fix-only.

## 1. Bring everything up cleanly

```bash
bash backend/scripts/demo-up.sh
# (or on Windows: powershell -File backend/scripts/demo-up.ps1)
tail -f out/demo.log
```

- [ ] `python` healthy on :7777
- [ ] `bridge` healthy on :3001 (Stagehand prewarm logs `[stagehand] ready`)
- [ ] No red `Error` lines in the first 30 seconds of `demo.log`

## 2. Re-run the four verified externals

These take ~90 seconds combined and protect against silent regressions.

```bash
node    backend/node/scripts/test-tts.js          # B1 — ElevenLabs Sage clone
python  backend/py/scripts/test_snowflake.py      # B2 — Snowflake round-trip
node    backend/node/scripts/test-stagehand.js    # B3 — Stagehand → Amazon
node    backend/node/scripts/test-stt.js          # B4 — OpenAI STT
```

- [ ] B1 prints `✓ first-byte: <X> | total bytes: <Y>` with X < 400ms
- [ ] B2 prints `✓ Snowflake round-trip ok`
- [ ] B3 prints `✓ Stagehand ok | <title> | $<price>`
- [ ] B4 prints `✓ STT: "..."` matching the synthesized line

## 3. Patient + history present

- [ ] `python backend/py/scripts/seed.py` — `Eleanor Hayes` row exists
- [ ] `python backend/py/scripts/seed_history.py` — 30 rows in `cognitive_analyses`,
      scores between ~62 and 100, with the dip at d-5

## 4. Cortex Analyst answers the demo question

```bash
python backend/py/scripts/upload_cortex_model.py        # if not already done
curl -s -X POST localhost:7777/caregiver/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What changed in today'\''s session compared to the last three?"}' | jq
```

- [ ] Response has `sql`, `rows`, and a one-sentence `answer_text`
- [ ] No `cortex analyst error: ...` (if you see that, Cortex Analyst is not
      enabled on your Snowflake account — Snowsight → Admin → Features)

## 5. One full e2e turn under 30 seconds

- [ ] Patient says: "I need a weekly pill organizer"
- [ ] Orb cycles `listening → thinking → speaking → complete` once
- [ ] Voice plays via the **Sage clone** (not generic ElevenLabs)
- [ ] Bridge log shows `[tts] ok engine=elevenlabs ms=<300–500>`
- [ ] Total wall-clock from speech end to voice start < 30s

## 6. Fallbacks rehearsed

```bash
bash backend/scripts/chaos.sh
```

- [ ] TTS fallback: pull the ElevenLabs key, retry — voice still plays via OpenAI
      (`tts:fallback-engaged` socket event observed)
- [ ] Browser fallback: ask for an absurd item — Sage says
      *"I had trouble finding that on Amazon just now…"* (the canned graceful line)
- [ ] Snowflake fallback: bad password → bridge does **not** crash, JSON appears
      in `out/failed-writes/`

## 7. Caregiver dashboard reads

```bash
curl -s 'localhost:7777/caregiver/overview?patient_id=p_eleanor' | jq
curl -s 'localhost:7777/caregiver/trend?patient_id=p_eleanor&days=30'  | jq '.points | length'
curl -s 'localhost:7777/caregiver/sessions?patient_id=p_eleanor&limit=5' | jq
```

- [ ] `overview` returns Eleanor + a non-null `latest_score`
- [ ] `trend` returns 30 points
- [ ] `sessions` returns 5 rows with `score` populated

## 8. Cost line at session end

After one e2e turn → `session:end`, the bridge log should contain:

```
Session p_eleanor:<uuid> cost: $0.0xxx (LLM $0.00xx in=N out=N | TTS $0.0xxx chars=N)
```

- [ ] Single cost line per session, total under ~$0.10 for a 1-minute demo

## 9. Stop cleanly

```bash
bash backend/scripts/demo-down.sh
```

---

When all boxes are checked, append to `CLAUDE.md` `## Build log`:
`- <ISO date> | A | DRESS REHEARSAL PASSED`
