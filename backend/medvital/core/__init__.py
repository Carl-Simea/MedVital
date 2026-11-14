"""Shared, framework-free core: schema, provenance, statistics, simulation.

Nothing in this package may import FastAPI, the API layer, the database layer or any
individual health module. Health modules depend on core; core never depends on them.
"""
