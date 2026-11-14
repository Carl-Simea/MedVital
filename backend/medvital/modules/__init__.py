"""The four independent health modules.

Each sub-package may import ``medvital.core`` only. Modules must never import each other, the
API layer or the database layer (enforced by tests/test_architecture.py).
"""
