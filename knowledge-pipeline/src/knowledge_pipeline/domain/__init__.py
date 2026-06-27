"""Domain layer — typed, I/O-free models + the north-star grid constants.

A domain type never imports an adapter, a network client, or sqlite. It is the vocabulary the pure
functions and the orchestration speak in.
"""
