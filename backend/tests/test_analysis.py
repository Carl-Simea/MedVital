"""Cross-domain analysis: calculations, engine and its architecture rules.

Merged from: test_analysis_calculations.py, test_analysis_engine.py, test_analysis_architecture.py."""

import ast
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from conftest import T0, make_obs, measured_provenance
from medvital.analysis import AnalysisConfig, BaselineSpec, analyze
from medvital.analysis import calculations as calc
from medvital.core.schema import DataOrigin, Quality
from medvital.registry import build_registry
from medvital.simulation.generator import generate_observations
from medvital.simulation.profiles import SIMULATED_PROFILES

# ---------------------------------------------------------------------- from test_analysis_calculations.py

def test_describe_hand_computed():
    # [1,2,3,4,10]: mean 4; deviations -3,-2,-1,0,6 -> SS 50 -> var 12.5 -> sd 3.5355339
    # quartiles (linear) 2 and 4; |x-3| = 2,1,0,1,7 -> MAD 1
    s = calc.describe(np.array([1, 2, 3, 4, 10]))
    assert s.count == 5
    assert s.mean == pytest.approx(4.0)
    assert s.std == pytest.approx(math.sqrt(12.5))
    assert (s.median, s.q1, s.q3, s.iqr, s.mad) == (3.0, 2.0, 4.0, 2.0, 1.0)
    assert (s.minimum, s.maximum) == (1.0, 10.0)


def test_describe_single_value_has_no_sd_and_rejects_bad_input():
    assert calc.describe(np.array([5.0])).std is None
    with pytest.raises(ValueError):
        calc.describe(np.array([]))
    with pytest.raises(ValueError):
        calc.describe(np.array([1.0, np.nan]))
    with pytest.raises(ValueError):
        calc.describe(np.ones((2, 2)))


def test_deviations_from_baseline_hand_computed():
    # baseline [1..5]: median 3, MAD 1, mean 3, sd sqrt(2.5)=1.5811388
    base = calc.describe(np.array([1, 2, 3, 4, 5]))
    d = calc.deviations_from_baseline(np.array([6.0, 9.0]), base)
    assert d.delta.tolist() == [3.0, 6.0]
    assert d.modified_z == pytest.approx([0.6745 * 3, 0.6745 * 6])  # 2.0235, 4.047
    assert d.z == pytest.approx([3 / math.sqrt(2.5), 6 / math.sqrt(2.5)])


def test_zero_spread_baseline_gives_undefined_scores():
    base = calc.describe(np.array([2.0, 2.0, 2.0, 2.0]))
    d = calc.deviations_from_baseline(np.array([3.0]), base)
    assert d.delta.tolist() == [1.0]
    assert np.isnan(d.z).all() and np.isnan(d.modified_z).all()


def test_flag_modified_z():
    flags = calc.flag_modified_z(np.array([2.0235, 4.047, -3.6, np.nan]), cutoff=3.5)
    assert flags.tolist() == [False, True, True, False]
    with pytest.raises(ValueError):
        calc.flag_modified_z(np.array([1.0]), cutoff=0)


def test_masks():
    assert calc.first_n_mask(5, 3).tolist() == [True, True, True, False, False]
    assert calc.first_n_mask(2, 3).tolist() == [True, True]
    assert calc.window_mask(np.array([0.0, 5.0, 10.0]), 0.0, 10.0).tolist() == [True, True, False]
    with pytest.raises(ValueError):
        calc.window_mask(np.array([0.0]), 5.0, 5.0)


def test_sampling_measures_hand_computed():
    t = np.array([0.0, 60.0, 120.0, 400.0, 460.0])
    # diffs 60,60,280,60 -> median 60; 280 > 2*60 is the only gap
    assert calc.median_interval(t) == 60.0
    gaps = calc.find_gaps(t, 60.0, 2.0)
    assert [(g.start_index, g.end_index, g.duration_s) for g in gaps] == [(2, 3, 280.0)]
    # floor(460/60)+1 = 8 expected; 5 observed -> 0.625
    assert calc.expected_count(t, 60.0) == 8
    assert calc.coverage_fraction(t, 60.0) == pytest.approx(0.625)


def test_duplicates_and_degenerate_sampling():
    assert calc.count_duplicate_times(np.array([0.0, 0.0, 60.0])) == 1
    assert calc.median_interval(np.array([5.0, 5.0])) is None
    assert calc.find_gaps(np.array([5.0]), 60.0, 2.0) == []
    with pytest.raises(ValueError):
        calc.find_gaps(np.array([0.0, 1.0]), 0.0, 2.0)


# ---------------------------------------------------------------------- from test_analysis_engine.py

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
    valid = _sleep_series([1, 2])
    suspect = [o.model_copy(update={"quality": Quality.SUSPECT}) for o in _sleep_series([100, 200])]
    invalid = [make_obs(SLEEP, 300.0, day=5).model_copy(update={"quality": Quality.INVALID})]
    report = analyze(valid + suspect + invalid)
    (s,) = report.series  # quality never splits a series; it only filters
    assert s.descriptive.count == 2 and s.descriptive.maximum == 2.0
    assert s.quality.quality_counts == {"invalid": 1, "suspect": 2, "valid": 2}
    assert s.quality.excluded_counts == {"quality": 3} and s.quality.total_count == 5
    assert sorted(e.detail for e in report.excluded) == [
        "quality=invalid",
        "quality=suspect",
        "quality=suspect",
    ]


def test_suspect_can_be_opted_in_and_unknown_quality_rejected():
    obs = [o.model_copy(update={"quality": Quality.SUSPECT}) for o in _sleep_series([1, 2])]
    (s,) = analyze(obs, AnalysisConfig(analyzed_qualities=(Quality.VALID, Quality.SUSPECT))).series
    assert s.quality.analyzed_count == 2
    with pytest.raises(ValueError):
        AnalysisConfig(analyzed_qualities=("unspecified",))


def test_devices_are_never_pooled():
    a = [o.model_copy(update={"device_id": "W1"}) for o in _sleep_series([1, 2])]
    b = [o.model_copy(update={"device_id": "W2"}) for o in _sleep_series([1, 2])]
    assert sorted(s.key.device_id for s in analyze(a + b).series) == ["W1", "W2"]


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


# ---------------------------------------------------------------------- from test_analysis_architecture.py

ROOT = Path(__file__).resolve().parents[1] / "medvital"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.add("<relative>")
            elif node.module:
                found.add(node.module)
    return found


def test_analysis_calculations_are_pure():
    forbidden = (
        "medvital",
        "fastapi",
        "pydantic",
        "requests",
        "httpx",
        "os",
        "pathlib",
        "sqlite3",
        "<relative>",
    )
    for name in _imports(ROOT / "analysis" / "calculations.py"):
        assert name.split(".")[0] not in forbidden, f"analysis/calculations.py imports {name}"


def test_analysis_depends_only_on_core_and_itself():
    for path in (ROOT / "analysis").rglob("*.py"):
        for name in _imports(path):
            if name == "medvital" or name.startswith("medvital."):
                assert name.startswith(("medvital.core", "medvital.analysis")), f"{path.name} imports {name}"


def test_nothing_below_api_imports_analysis():
    for sub in ("core", "modules", "simulation", "db"):
        for path in (ROOT / sub).rglob("*.py"):
            assert not any(n.startswith("medvital.analysis") for n in _imports(path)), path
