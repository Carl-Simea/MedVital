# Non-Clinical Rule Engine

Implementation: `backend/medvital/rules.py` (rules version 1). Decision: D-021. Tests: `tests/test_rules.py`.

The engine produces `RuleFinding` **review flags**. Two marker fields are fixed: `clinical=False` and
`review_required=True`.

It never:
* applies a clinical threshold;
* labels a person's risk or health;
* creates, changes, delays or suppresses a RETURN_NOW command.

A static test asserts that the module imports no command function. A dynamic test asserts that a stored command is
unchanged after evaluation.

## Rules

| Rule | Fires when | Operational parameter (engineering default) | Evidence |
|---|---|---|---|
| `device_offline` | A device's newest observation is older than the limit | `device_offline_after_s = 300` | Device and last time |
| `invalid_sensor_data` | Non-`valid` readings (`suspect`/`invalid`) in the window | `invalid_data_window_s = 3600` | `observation_id:quality` |
| `missed_scheduled_measurement` | A planned window (resolved from the mission time model) has closed with no observation of any origin. For an ongoing mission, return-anchored events are not yet due. | none; the schedule defines the window | Schedule id |
| `sync_failure` | An upstream refused observations or records in the window | `sync_failure_window_s = 86400` | `observation_id:error` |
| `space_weather_notice` | A DONKI event or notice in the look-back window. RAD detector series are context, not notices. | `space_weather_lookback_s = 86400` | Event id |
| `statistical_deviation_review` | The analysis engine flags \|modified z\| > cutoff against the subject's **own** baseline | `deviation_window_s = 604800`, plus the analysis config (cutoff 3.5, Iglewicz & Hoaglin) | Observation id |

The parameters are configurable per evaluation (`RuleConfig`). None of them is a clinical or scientific value, and each
finding records the parameters that produced it.

## Determinism and storage

* **Finding ids** are uuid5(rule, key). The key is built from the triggering facts (device and last time, schedule and
  event, event id, observation id). Re-evaluating identical data gives identical ids, and storing again is a
  duplicate.
* **Evaluation is a pure read.** `POST /rules/evaluate {persist: true}` stores the findings.
* **Findings are filtered by caller scope.** Subject-less findings, such as space weather, are visible to every
  permitted caller.

## RETURN_NOW (human-issued only)

* **What the command records:** issuer (`principal_id`, name, role: flight surgeon, ground control or mission
  commander), issue time, mission, optional crew subset, reason and mission context.
* **Status history** is append-only: issued → acknowledged → in_progress → completed, and every non-terminal state may
  go to withdrawn. Invalid transitions and times earlier than the previous status are rejected. The command record
  never changes.
* **Replication:** the command reaches other stations by document pull, with its history preserved (D-030).
* **No automation:** no rule, AI component or service principal can issue or change it. This holds in the model
  (`issuer_type="human"`), in authorization (`human` principals only, in their own name) and in code (the rule engine
  has no command import).

## Limitations

* `statistical_deviation_review` analyses up to 100,000 observations per evaluation. That is fine for the demo, but
  larger stores need windowed queries.
* No rule de-duplication across categories. One device can be both offline and have invalid data.
* `sync_failure` sees only *refusals*. Upstream *unavailability* appears in delivery reports, not as findings.
