"""Analysis engine behaviour: origin separation, baselines, exclusions, missingness, JSON."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from conftest import T0, make_obs, measured_provenance
from medvital.analysis import AnalysisConfig, BaselineSpec, analyze
from medvital.core.schema import DataOrigin
from medvital.registry import build_registry
from medvital.simulation.generator import generate_observations
from medvital.simulation.profiles import SIMULATED_PROFILES

SLEEP = "behavioral.sleep_duration"
DAY = 86400.0


def _sleep_series(values, **kw):
    return [make_obs(SLEEP, v, day=i, **kw) for i, v in enumerate(values)]


def _cfg(**kw):
    return AnalysisConfig(baseline=BaselineSpec(n=5), **kw)


def test_simulated_and_measured_are_separate_series():
    sim = _sleep_series([1, 2, 3])
    meas = _sleep_series([7, 8, 9], provenance=measured_provenance())
    report = analyze(sim + meas)
    origins = sorted(s.key.data_origin.value for s in report.series)
    assert origins == ["measured", "simulated"]
    by_origin = {s.key.data_origin: s for s in report.series}
    assert by_origin[DataOrigin.SIMULATED].descriptive.mean == pytest.approx(2.0)
    assert by_origin[DataOrigin.MEASURED].descriptive.mean == pytest.approx(8.0)
    assert by_origin[DataOrigin.MEASURED].provenance.source_refs == ["test://fixture/1"]


def test_context_and_subject_are_never_pooled():
    a = _sleep_series([1, 2], context={"device": "A"})
    b = _sleep_series([1, 2], context={"device": "B"})
    c = _sleep_series([1, 2], subject_id="SIM-T02")
    assert len(analyze(a + b + c).series) == 3


def test_baseline_deviation_and_anomaly_hand_computed():
    # baseline [1..5] median 3 MAD 1; 6 -> M=2.0235 (not flagged), 9 -> M=4.047 (flagged)
    report = analyze(_sleep_series([1, 2, 3, 4, 5, 6, 9]), _cfg(include_point_deviations=True))
    (s,) = report.series
    assert s.baseline.count == 5 and s.baseline.stats.median == 3.0 and s.baseline.stats.mad == 1.0
    assert [d.modified_z for d in s.deviations] == pytest.approx([2.0235, 4.047])
    assert s.latest_deviation.value == 9.0 and s.latest_deviation.delta_from_baseline_median == 6.0
    (flag,) = s.anomalies
    assert flag.value == 9.0 and flag.unit == "h" and flag.data_origin is DataOrigin.SIMULATED
    assert flag.observed_at == T0 + timedelta(days=6)
    assert flag.cutoff == 3.5


def test_point_deviations_are_opt_in():
    (s,) = analyze(_sleep_series([1, 2, 3, 4, 5, 6, 9]), _cfg()).series
    assert s.deviations == [] and s.latest_deviation is not None


def test_time_window_baseline():
    spec = BaselineSpec(mode="time_window", start=T0, end=T0 + timedelta(days=5), min_count=4)
    (s,) = analyze(_sleep_series([1, 2, 3, 4, 5, 9]), AnalysisConfig(baseline=spec)).series
    assert s.baseline.count == 5 and len(s.anomalies) == 1


def test_short_baseline_warns_instead_of_guessing():
    (s,) = analyze(_sleep_series([1, 2, 3]), _cfg()).series
    assert s.baseline is None and s.anomalies == []
    assert any("baseline has 3" in w for w in s.warnings)


def test_zero_mad_baseline_never_flags():
    (s,) = analyze(_sleep_series([2, 2, 2, 2, 2, 50]), _cfg()).series
    assert s.anomalies == [] and s.latest_deviation.modified_z is None
    assert any("MAD is zero" in w for w in s.warnings)


def test_superseded_observation_is_excluded_and_reported():
    original = make_obs(SLEEP, 100.0, day=0)
    correction = make_obs(SLEEP, 7.0, day=0).model_copy(update={"supersedes": original.id})
    report = analyze([original, correction])
    (s,) = report.series
    assert s.descriptive.count == 1 and s.descriptive.mean == 7.0
    assert s.quality.excluded_counts == {"superseded": 1} and s.quality.total_count == 2
    assert [(e.observation_id, e.reason.value) for e in report.excluded] == [(str(original.id), "superseded")]


def test_registry_rejections_are_reported_not_dropped():
    bad = make_obs(SLEEP, 7.0, unit="min")  # non-canonical unit
    report = analyze([bad, make_obs(SLEEP, 7.0)], registry=build_registry())
    assert report.input_count == 2 and report.analyzed_count == 1
    (rej,) = report.excluded
    assert rej.reason.value == "rejected" and "canonical unit" in rej.detail


def test_quality_filter_excludes_and_counts():
    report = analyze(_sleep_series([1, 2]), AnalysisConfig(analyzed_qualities=("valid",)))
    (s,) = report.series
    assert s.descriptive is None and s.quality.analyzed_count == 0
    assert s.quality.quality_counts == {"unspecified": 2} and s.quality.excluded_counts == {"quality": 2}
    assert len(report.excluded) == 2


def test_gaps_and_coverage_with_configured_interval():
    obs = [make_obs(SLEEP, 7.0, day=d) for d in (0, 1, 2, 6, 7)]
    (s,) = analyze(obs, AnalysisConfig(expected_interval_s={SLEEP: DAY})).series
    q = s.quality
    assert q.interval_source == "configured" and q.expected_count == 8
    assert q.coverage_fraction == pytest.approx(5 / 8)
    (gap,) = q.gaps
    assert gap.duration_s == 4 * DAY
    assert gap.after == T0 + timedelta(days=2) and gap.before == T0 + timedelta(days=6)


def test_inferred_interval_and_duplicate_timestamps():
    obs = [make_obs(SLEEP, 7.0, day=d) for d in (0, 0, 1, 2)]
    (s,) = analyze(obs).series
    assert s.quality.interval_source == "inferred" and s.quality.expected_interval_s == DAY
    assert s.quality.duplicate_timestamps == 1


def test_missing_expected_metrics_are_reported():
    report = analyze(_sleep_series([7.0]), AnalysisConfig(expected_metrics=(SLEEP, "bone.areal_bmd")))
    assert [(m.subject_id, m.metric) for m in report.missing_series] == [("SIM-T01", "bone.areal_bmd")]


def test_report_is_strict_json_and_free_of_risk_labels():
    report = analyze(_sleep_series([2, 2, 2, 2, 2, 50]), _cfg(include_point_deviations=True))
    text = json.dumps(report.model_dump(mode="json"), allow_nan=False)
    assert json.loads(text)["notice"]
    lowered = text.lower()
    for label in ("abnormal", "at risk", "healthy", "critical", "high risk"):
        assert label not in lowered


def test_timestamps_and_units_preserved():
    at = datetime(2030, 3, 1, 12, 30, 15, tzinfo=UTC)
    o = make_obs(SLEEP, 7.0).model_copy(update={"observed_at": at, "id": uuid4()})
    (s,) = analyze([o]).series
    assert s.first_observed_at == at and s.key.unit == "h"


def test_simulated_profile_end_to_end():
    profile = SIMULATED_PROFILES[0]
    obs = generate_observations(profile, start=T0, days=30, seed=7)
    report = analyze(obs, registry=build_registry())
    assert report.excluded == [] and report.analyzed_count == len(obs)
    assert {s.key.data_origin for s in report.series} == {DataOrigin.SIMULATED}
    json.dumps(report.model_dump(mode="json"), allow_nan=False)
