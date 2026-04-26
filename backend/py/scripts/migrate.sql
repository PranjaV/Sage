-- Sage core schema. Idempotent — safe to re-run.

CREATE TABLE IF NOT EXISTS patients (
  patient_id     STRING,
  name           STRING,
  age            INT,
  caregiver_name STRING,
  baseline_score INT,
  consent_status STRING
);

CREATE TABLE IF NOT EXISTS patient_profile (
  patient_id    STRING,
  doctors       VARIANT,
  appointments  VARIANT,
  pharmacy      VARIANT,
  address       VARIANT,
  common_items  VARIANT
);

CREATE TABLE IF NOT EXISTS sessions (
  session_id       STRING,
  patient_id       STRING,
  started_at       TIMESTAMP_NTZ,
  ended_at         TIMESTAMP_NTZ,
  transcript       STRING,
  duration_seconds INT,
  primary_task     STRING
);

CREATE TABLE IF NOT EXISTS interactions (
  interaction_id STRING,
  session_id     STRING,
  speaker        STRING,
  utterance      STRING,
  created_at     TIMESTAMP_NTZ
);

CREATE TABLE IF NOT EXISTS cognitive_analyses (
  analysis_id     STRING,
  session_id      STRING,
  patient_id      STRING,
  overall_score   INT,
  severity        STRING,
  baseline_delta  INT,
  metrics         VARIANT,
  flagged_phrases VARIANT,
  summary         STRING,
  analyzed_at     TIMESTAMP_NTZ
);

CREATE TABLE IF NOT EXISTS caregiver_alerts (
  alert_id     STRING,
  patient_id   STRING,
  session_id   STRING,
  trigger_type STRING,
  sent_at      TIMESTAMP_NTZ
);
