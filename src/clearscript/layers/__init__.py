"""Edit layers.

In v0.0.1 the layer logic lives entirely in the LLM prompts at
``clearscript/prompts/layers/``. This package will host Python-side helpers
(deterministic pre/post-processors, validators, audit-trail builders) starting
in v0.1, where each layer's prompt is paired with a small Python module that
verifies the LLM's adherence to the layer's contract.
"""
