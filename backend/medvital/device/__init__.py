"""Simulated astronaut wearable (software only).

Run one process per device:  ``python -m medvital.device --device-id MEDVITAL-WEARABLE-001``

Everything a device emits is **synthetic**: ``synthetic: true`` with a generator version and
seed. Signal magnitudes are arbitrary test values, not derived from NASA data or any person.
The package depends only on ``medvital.core`` and the standard library (it must run on small
machines such as a Raspberry Pi).
"""
