"""Simulated astronaut profile model.

Profiles are parameter sets for the simulator. They describe NO real person. Parameter values
are illustrative developer choices and are not derived from any NASA dataset.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from medvital.core.observation import ASTRONAUT_ID_PATTERN


class SimParameter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mean: float
    sd: float = Field(ge=0)
    # Linear change per simulated day. Defaults to 0: the simulator does not assume any
    # spaceflight effect unless a scenario explicitly asks for one.
    drift_per_day: float = 0.0


class AstronautProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(pattern=ASTRONAUT_ID_PATTERN)
    display_name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=400)
    # Keyed by metric name (metric names are unique across modules).
    parameters: dict[str, SimParameter]
    is_simulated: Literal[True] = True
