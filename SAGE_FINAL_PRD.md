# SAGE - Product Requirements Document

Date: April 25, 2026  
Audience: hackathon team, design support, engineering support, demo prep

---

## 1. The One-Line Truth

> *Sage is the AI support layer for elderly independence - a system where the computer becomes invisible to the person who needs help, and meaningful cognitive signals become visible to the people who care for them.*

---

## 2. The Problem (How You Open Every Conversation With a Judge)

Say the scene. Do not start with the stack.

An older adult is living alone. She needs to refill medication, order a pill organizer, or make sure she can get to a doctor's appointment. The barrier is not willingness. The barrier is modern software. Small text. Passwords. Multi-step flows. Popups. Confusing confirmations. Too many places to fail.

Her daughter is in another city. She hears, "I think Mom is doing okay," or "She sounded a little off this week," but she has no structured way to tell the difference between an ordinary rough day and the beginning of something that deserves attention.

Siri can play a song. Alexa can set a timer. Neither of them can take a messy spoken request, complete a meaningful digital task, keep context across the conversation, and then give a caregiver a clear picture of what happened afterward.

Sage does all of that from one natural sentence, with consent, without making the user fight a screen.

---

## 3. What Sage Actually Is

Sage is **not** a chatbot. It is **not** a dashboard with a microphone attached. It is an ambient support layer that wraps around a computer and turns modern interfaces into something a person can simply talk to.

It has two very different faces:

**Face 1 - The Older Adult Experience:**  
There is no workflow to learn. No menu tree to memorize. No app to "figure out." Sage is present, calm, and ready when activated. The user speaks naturally, messily, incompletely - the way real people actually talk. Sage figures out the intent, handles the task, and confirms what happened in a warm voice. The technology recedes.

**Face 2 - The Caregiver Experience:**  
A separate intelligence dashboard built from consented interactions. Caregivers see session summaries, cognitive-signal trends, highlighted transcript evidence, and can query the full session history in plain English. The point is not diagnosis. The point is visibility, pattern recognition, and earlier follow-up.

One product. One codebase. Two users who should never feel like they are using the same interface.

---

## 4. Target Users

**Primary user - The older adult (65+):**  
Lives independently or semi-independently. Struggles with modern websites, small text, long flows, and account friction. May have mild cognitive changes, but does not want to feel medicalized. Wants dignity. Wants independence. Has no patience for technology that makes them feel lost.

**Secondary user - The caregiver or family member:**  
Often remote. Often anxious. Currently forced to assess change through scattered phone calls and intuition. Wants something more concrete than anecdotes, but more humane than a clinical portal.

**Implicit third user - The blind or visually impaired user:**  
The same product serves them naturally. Voice in, task out, low dependence on the screen. This is a real multiplier, not a separate mode bolted on later.

---

## 5. Complete Tech Stack

### 5.1 Frontend - Older Adult Experience (Electron Overlay)

| Component | Technology | Source | Notes |
|---|---|---|---|
| Desktop shell | Electron | VisionOS pattern | Persistent overlay, calm chrome, lightweight surface |
| Orb visual | React + CSS/Canvas animation | VisionOS adapted | Warm amber/gold, subtle pulse, dignified not flashy |
| Transcript rail | React in Electron | VisionOS adapted | Visible in demo mode; hidden or minimized in patient mode |
| Agent trace | LangGraph event stream | VisionOS adapted | Only for judges and debugging, not core patient UI |
| Browser execution surface | Stagehand-controlled Chromium | VisionOS pattern | Judges can watch one meaningful task happen live |
| Session status chip | New React component | New | Small "listening / thinking / completed" state for demo clarity |

### 5.2 Frontend - Caregiver Dashboard (Next.js Web App)

| Component | Technology | Source | Notes |
|---|---|---|---|
| Dashboard shell | Next.js | Bloom adapted | Separate interface, separate emotional tone |
| Score and trend cards | React + charting | Bloom adapted | Latest score plus short trend windows |
| Annotated transcript | React | Bloom adapted | Evidence phrases highlighted with plain-English labels |
| Session list | React | Bloom adapted | Date, score, severity, summary preview |
| Ask Sage input | New component | New | Plain English -> Cortex Analyst query -> result |
| Session summary card | React | Bloom adapted | Simple, readable, non-clinical language |

### 5.3 Backend

| Component | Technology | Source | Notes |
|---|---|---|---|
| Agent orchestrator | LangGraph | VisionOS pattern | Multi-step routing, stateful task flow |
| Supervisor / routing model | OpenAI `gpt-4.1-mini` | OpenAI + VisionOS pattern | Fast intent routing and recovery logic |
| Browser execution model | OpenAI `gpt-4.1` | OpenAI + VisionOS pattern | Higher-reliability model for live web work |
| Voice STT | OpenAI `gpt-4o-mini-transcribe` | OpenAI | Low-cost transcription path |
| Voice TTS | ElevenLabs `Flash v2.5` (custom Sage voice clone) | ElevenLabs Pro | 75ms latency, warm custom voice; fallback to OpenAI `gpt-4o-mini-tts` if needed |
| Cognitive scoring core | Deterministic transcript analyzer | Bloom adapted | Primary signals come from measurable transcript markers |
| Caregiver summary model | OpenAI `gpt-5-mini` | OpenAI | Turns metrics into readable summaries and follow-up prompts |
| Web automation | Stagehand | VisionOS pattern | One reliable live browser flow is the standard |
| Data warehouse | Snowflake | Backend PRD | Sessions, analyses, baselines, patient context |
| Natural-language caregiver queries | Snowflake Cortex Analyst | Backend PRD | Plain English to SQL to chart and answer |
| Transform jobs | Snowpark | Backend PRD | Trend aggregation and derived session metrics |

### 5.4 What Was Dropped and Why

| Dropped | Reason |
|---|---|
| Deepgram | OpenAI handles the speech layer now |
| Realtime API as core voice path | More complexity than needed for the demo |
| Realtime API as the core voice path | More complexity than we need for the demo |
| Hidden or passive monitoring language | Dangerous for judging and wrong for the product |
| Multiple live websites as a requirement | Too brittle for a winning demo |
| Semantic memory as a critical-path dependency | Structured patient context is enough to prove the point |
| Simultaneous caregiver live sync | Not needed to win the story or the demo |

---

## 6. Feature Stack - Complete

### 6.1 Core Features (Must Ship)

**F1 - Voice-First Task Automation**  
The user speaks in natural language. Sage interprets the request, plans the task, opens the browser when needed, completes the work, and confirms the outcome in a calm voice.

Hardcoded demo flows:
- Primary live flow: Amazon medical item search and order flow
- Secondary support flow: doctor-context retrieval, ride planning, or reminder creation using stored patient context

Important: the product only needs **one** live web flow to succeed on stage. Everything else must be designed so the demo still wins if the second action stays inside Sage instead of going to another third-party site.

**F2 - Structured Patient Context**  
Sage knows the essentials that matter in a care scenario:
- caregiver name
- doctor names
- appointment context
- address
- preferred pharmacy
- common health-item orders

For the hackathon build, this is stored as structured data in Snowflake first. If Cortex Search lands later, great. It is not required for the core story.

**F3 - Empathetic Response Layer**  
Sage does not sound transactional. It responds like a calm helper. When the user sounds uncertain, repeats themselves, or speaks vaguely, Sage stabilizes the interaction before pushing the task forward. This matters for trust, and it matters for the design track.

**F4 - Consent-Based Cognitive Signal Analysis**  
After each session ends, the full transcript is analyzed for measurable speech and language markers:
- repetition
- pauses and hesitation markers
- lexical diversity
- word-finding patterns
- circumlocution
- self-correction
- topic drift
- repeated asks

The output is not a diagnosis. It is a structured session score, evidence phrases, severity label, and caregiver-facing summary that helps someone notice change over time.

**F5 - Caregiver Intelligence Dashboard**  
The caregiver sees:
- latest score
- short trend windows
- full transcript with highlighted evidence phrases
- session summaries
- suggested next-step prompts or exercises

This is where Sage stops being a cool demo and starts feeling like a real product.

**F6 - Ask Sage with Cortex Analyst**  
The caregiver can ask plain-English questions like:
- "Has her word-finding gotten worse this month?"
- "How many sessions this week looked more concerning than her baseline?"
- "What changed in today's session compared to the last three?"

Cortex Analyst handles the query layer. The result should feel like data made legible, not BI theater.

### 6.2 Polish Features (Build If Time)

**P1 - Medication reminder surface**  
Simple reminder chip or spoken reminder, not a giant scheduling system.

**P2 - Caregiver alerting**  
Trigger when a session meaningfully deviates from recent baseline.

**P3 - Doctor-ready export**  
Clean PDF or print view of a session summary plus transcript evidence.

---

## 7. UI Breakdown - What You See When You Open Sage

### 7.1 What the older adult sees

The patient interface should feel almost empty.

**Zone 1 - The Orb**  
A warm amber/gold orb, always visually calm. States:
- Idle
- Listening
- Thinking
- Speaking
- Complete

This is the emotional anchor of the product. It cannot feel cold, technical, or sci-fi.

**Zone 2 - Browser stage, only when needed**  
When Sage needs to perform a web task, the browser becomes visible and large enough for judges to understand the action. Outside of task execution, it should recede.

**Zone 3 - Minimal confirmation surface**  
Simple text or voice confirmation that the task completed, what was done, and what happens next.

### 7.2 What judges see in demo mode

Judges need a little more visibility than the patient does. Demo mode can show:
- a transcript rail
- a compact reasoning trace
- session status chip

This is not because the patient needs it. It is because the audience needs to understand the intelligence under the hood without cluttering the real product.

### 7.3 The caregiver dashboard

**Header:** patient name, last active, current status

**Left rail:** session history list with score and timestamp

**Main area:** four clear views
1. Overview - latest score, trend, summary
2. Transcript - highlighted evidence phrases
3. Trends - recent score and marker change over time
4. Ask Sage - natural-language query powered by Cortex Analyst

The dashboard should feel trustworthy, quiet, and humane. Not sterile. Not overdesigned. Not like a hospital portal.

---

## 8. The Cognitive Analysis - Technical Detail

This is what makes Sage more than browser automation.

The analysis runs **after** the session ends. It never blocks the live voice loop.

### Step 1 - Deterministic scoring pass

Adapt Bloom's transcript-analysis approach into a local scoring engine that measures:
- lexical diversity
- repetition
- pause and hesitation markers
- pronoun drift
- word-finding patterns
- self-corrections
- topic coherence

This gives us a stable, explainable base score.

### Step 2 - OpenAI interpretation pass

Use `gpt-5-mini` to transform the transcript plus deterministic metrics into:
- a short caregiver summary
- a trend note
- suggested follow-up prompts or exercises
- readable labels for the highlighted evidence

### Step 3 - Highlight mapping

Store transcript evidence with exact spans when possible. If a phrase cannot be matched safely, do not fake a highlight. The UI should only render evidence we can defend.

### Output shape

```json
{
  "overall_score": 78,
  "severity": "watch",
  "baseline_delta": -6,
  "metrics": {
    "lexical_diversity": 0.61,
    "repetition_count": 2,
    "hesitation_count": 5,
    "topic_drift_count": 1
  },
  "flagged_phrases": [
    {
      "phrase": "the blood pressure one",
      "label": "word-finding",
      "severity": "medium"
    }
  ],
  "session_summary": "She completed the task successfully but showed more hesitation and one word-finding moment compared with recent sessions.",
  "suggested_exercises": [
    "Follow up with a simple naming task later this week.",
    "Listen for repeated medication questions over the next few sessions."
  ]
}
```

Rule: higher score means lower concern. Keep that consistent everywhere.

---

## 9. Data Architecture

```text
Snowflake Schema:

patients
  - patient_id, name, age, caregiver_name, baseline_score, consent_status

patient_profile
  - patient_id, doctors (JSON), appointments (JSON), pharmacy (JSON), address (JSON), common_items (JSON)

sessions
  - session_id, patient_id, started_at, ended_at, transcript, duration_seconds, primary_task

interactions
  - interaction_id, session_id, speaker, utterance, created_at

cognitive_analyses
  - analysis_id, session_id, patient_id, overall_score, severity, baseline_delta, metrics (JSON), flagged_phrases (JSON), summary, analyzed_at

caregiver_alerts
  - alert_id, patient_id, session_id, trigger_type, sent_at
```

Cortex Analyst sits on top of `sessions`, `cognitive_analyses`, and `patient_profile` to answer caregiver questions in plain English.

Cortex Search is optional. If it lands, use it to enrich retrieval. If it does not, the product still works because patient context is already structured.

---

## 10. Development Phases - Build Order That Keeps Us Safe

### Phase 1 - Voice loop and shell

**Goal:** make Sage feel alive before it feels smart.

Build:
- Electron shell
- orb states
- Socket.IO event loop
- OpenAI STT (`gpt-4o-mini-transcribe`)
- ElevenLabs Flash v2.5 TTS (custom Sage voice)
- transcript accumulation

Done when:
- 10 repeated turns work without audio overlap
- speech starts and stops cleanly
- playback order is stable
- the orb states are always truthful

Test alongside:
- microphone permission flow
- sample-rate mismatch handling
- barge-in interruption
- cold start on the demo machine

### Phase 2 - One live browser task

**Goal:** make one web task work five times in a row.

Build:
- LangGraph supervisor
- Stagehand browser execution
- Amazon medical-item flow
- fallback path for timeouts or UI drift

Done when:
- the item search/order flow succeeds repeatedly
- Sage narrates what it is doing without sounding robotic
- failure fallback still feels graceful

Test alongside:
- Amazon login/session persistence
- slow network behavior
- browser recovery after a timeout
- visible demo readability from a distance

### Phase 3 - Session persistence and cognitive analysis

**Goal:** turn a finished conversation into a real caregiver artifact.

Build:
- Snowflake session writes
- deterministic scoring engine
- `gpt-5-mini` caregiver summary
- flagged-phrase storage
- baseline comparison

Done when:
- one live session appears in Snowflake
- the analysis result is stable across repeated transcript runs
- the output sounds grounded and non-diagnostic

Test alongside:
- golden transcripts: normal, mildly concerning, clearly concerning
- score direction correctness
- highlight span validity
- summary tone and safety

### Phase 4 - Caregiver dashboard

**Goal:** make the second half of the story feel inevitable.

Build:
- latest score card
- session list
- trend view
- transcript highlights
- one Ask Sage / Cortex Analyst query

Done when:
- seeded history plus one fresh session renders correctly
- judges can understand the dashboard in under 10 seconds
- the Ask Sage answer feels useful, not gimmicky

Test alongside:
- mobile and laptop layout sanity
- chart rendering with sparse and dense data
- query results with missing fields
- transcript highlight alignment

### Phase 5 - Demo polish and resilience

**Goal:** make the product win in the room, not just in the repo.

Build:
- seeded demo patient
- seeded prior sessions
- fallback copy for browser failure
- final voice tone tuning
- final color and spacing pass

Done when:
- the full demo runs start to finish in under 4 minutes
- everyone on the team can present it
- the product still lands emotionally if one moving part fails

Test alongside:
- full rehearsals with timing
- projector readability
- audio volume in a noisy room
- network hotspot fallback

---

## 11. The 4-Minute Demo That Wins

**Setup:** laptop on screen, Sage overlay visible, caregiver dashboard ready on a second tab or display.

---

**[0:00 - 0:08] The opening line**  
Presenter: *"This is a computer built for someone who should not have to fight a computer."*

---

**[0:08 - 1:20] The task**  
User: *"I need one of those weekly pill organizers, and I keep forgetting which one I got last time."*

Sage listens, confirms gently, opens Amazon, retrieves the familiar item context if available, and completes the search or order flow live.

Voice: *"I found the weekly pill organizer you usually get. I can order that now."*

Judges see one thing clearly: the user did not navigate anything.

---

**[1:20 - 2:00] The memory moment**  
User: *"And I need to get to Dr. Mehta on Thursday morning."*

Sage retrieves the stored doctor and appointment context, responds naturally, and either:
- prepares the ride or reminder flow inside Sage, or
- opens the secondary browser action only if it is already rock solid

This is where judges realize Sage is not stateless.

---

**[2:00 - 2:50] The flip**  
Switch to caregiver dashboard.

Show:
- today's score
- short trend view
- transcript highlights
- one Ask Sage question

Type: *"What changed in today's session compared to the last three?"*

The answer should show that the system is not just storing text. It is structuring it.

---

**[2:50 - 4:00] The close**  
Say it plainly:

*"Sage gives an older adult independence in the moment, and gives the people who love them visibility over time."*

*"It does not ask them to learn a new interface. It makes the interface disappear."*

*"And when something in their speech starts to change, the family sees a signal early enough to follow up."*

That is the close. Calm. Human. No hype spiral.

---

## 12. Track-by-Track Win Conditions

**OpenAI Track:**  
OpenAI powers the speech layer, the routing layer, the browser-execution intelligence, and the caregiver-language layer. This is an actual agentic product, not a chatbot wrapped around a UI.

**Snowflake Track:**  
Session history, cognitive analyses, patient context, and caregiver queries all live in Snowflake. Cortex Analyst makes the data feel conversational instead of buried.

**Healthcare / Tech for Good:**  
This is about independent living, caregiver support, and earlier follow-up. It gives families something more actionable than intuition without pretending to be a diagnosis engine.

**Design for Everyday Life:**  
The design thesis is restraint. The patient experience is calm and nearly invisible. The caregiver experience is information-dense but readable. The same product respects two emotional contexts without forcing either user into the wrong interface.

---

## 13. The Answer When Judges Ask Hard Questions

**"How is this different from Alexa?"**  
*"Alexa can answer a question. Sage can take a messy spoken request, complete a real task, remember the context around that person's care, and show a caregiver what changed afterward."*

**"Isn't this just browser automation?"**  
*"Browser automation is only one layer. The real product is the combination of ambient assistance, patient context, and caregiver-facing signal extraction."*

**"Are you diagnosing dementia?"**  
*"No. Sage surfaces patterns that may deserve attention. It is an early signal and follow-up tool, not a diagnostic system."*

**"How do you keep the analysis trustworthy?"**  
*"The score starts from deterministic transcript markers, then OpenAI turns that into a readable summary. We are not asking a model to invent a medical conclusion from thin air."*

**"What about privacy?"**  
*"The experience is consent-based. Data is stored for the caregiver-authorized workflow, not hidden surveillance. The patient and family know Sage is capturing and summarizing interactions."*

**"What if the live site fails?"**  
*"The product is designed to still tell a complete story with one successful browser task and a graceful fallback. Reliability is part of the design, not an afterthought."*

---

## 14. Operating Budget for Build and Demo

ChatGPT Plus does **not** cover API usage for Sage. The product needs OpenAI API credits.

For the hackathon build, the budget target is simple:

- put `20-25 USD` into OpenAI API credits
- use `gpt-4o-mini-transcribe` for STT
- use ElevenLabs `Flash v2.5` for TTS (you have Pro — no character budget concern for a demo)
- use `gpt-4.1-mini` for routing
- use `gpt-4.1` only where browser reliability matters
- use `gpt-5-mini` for post-session caregiver summaries

That is enough for development, rehearsal, and demo if the team is disciplined about prompt length and repeated testing.

Things that can blow the budget unnecessarily:
- switching the whole product to Realtime too early
- running very long rehearsal sessions all day without watching usage
- letting browser retries spiral
- sending giant transcript payloads over and over without trimming context

---

## 15. Code Integration Plan for Codex / Claude

```text
From visionOS - keep the patterns:
  Electron overlay shell
  Orb state model
  Socket-based voice loop
  LangGraph supervisor shape
  Stagehand browser wrapper

From visionOS - adapt:
  Model calls -> OpenAI-only stack
  UI chrome -> warmer, quieter patient experience
  Demo mode -> transcript rail and trace only when useful

From Bloom - extract and port:
  Deterministic transcript-analysis ideas
  Caregiver dashboard structure
  Summary and evidence presentation patterns

New code to write:
  OpenAI STT adapter
  ElevenLabs Flash v2.5 TTS adapter (custom Sage voice)
  Snowflake persistence layer
  Deterministic scoring module
  GPT-5-mini caregiver-summary prompt
  Ask Sage / Cortex Analyst UI
  Transcript highlight span-mapping logic
```

---

## 16. What Sage Is, In One Paragraph

Sage is an ambient AI support layer that helps an older adult complete meaningful digital tasks through natural speech while giving caregivers a clear, humane view of how those interactions are changing over time. It removes interface friction for the person who needs help, and it turns ordinary conversations into structured signals for the people trying to care well from a distance. It is not a diagnosis engine. It is not a voice gimmick. It is infrastructure for aging with more dignity, more independence, and less uncertainty.
