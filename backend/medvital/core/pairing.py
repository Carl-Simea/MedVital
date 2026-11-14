"""Pair observations of two metrics that describe the same measurement event.

Used for derived values that need two inputs (MAP from SBP+DBP, cardiac output from HR+SV, sleep
efficiency from sleep time + time in bed). A pair requires the *same* subject, data origin,
device, observation time and values of ``match_context_keys``. Only ``valid``-quality
observations are paired. If a key has more than one candidate on either side, it is ambiguous and
skipped (counted), never guessed. Nothing is interpolated.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from medvital.core.schema import HealthObservation, Quality

_Key = tuple[str, str, str, str, tuple[tuple[str, str], ...]]


@dataclass(frozen=True)
class Pair:
    a: HealthObservation
    b: HealthObservation


@dataclass
class PairingResult:
    pairs: list[Pair] = field(default_factory=list)
    unpaired_a: int = 0
    unpaired_b: int = 0
    ambiguous: int = 0


def _key(o: HealthObservation, keys: Sequence[str]) -> _Key:
    return (
        o.subject_id,
        o.provenance.data_origin.value,
        o.device_id or "",
        o.observed_at.isoformat(),
        tuple((k, o.context.get(k, "")) for k in keys),
    )


def pair_observations(
    observations: Iterable[HealthObservation],
    metric_a: str,
    metric_b: str,
    match_context_keys: Sequence[str] = (),
) -> PairingResult:
    side: dict[str, dict[_Key, list[HealthObservation]]] = {
        metric_a: defaultdict(list),
        metric_b: defaultdict(list),
    }
    for o in observations:
        if o.metric in side and o.quality is Quality.VALID:
            side[o.metric][_key(o, match_context_keys)].append(o)
    a_side, b_side = side[metric_a], side[metric_b]
    result = PairingResult()
    for k, a_list in a_side.items():
        b_list = b_side.get(k, [])
        if len(a_list) == 1 and len(b_list) == 1:
            result.pairs.append(Pair(a_list[0], b_list[0]))
        elif not b_list:
            result.unpaired_a += len(a_list)
        else:
            result.ambiguous += len(a_list) + len(b_list)
    result.unpaired_b += sum(len(v) for k, v in b_side.items() if k not in a_side)
    result.pairs.sort(key=lambda p: (p.a.observed_at, str(p.a.id)))
    return result
