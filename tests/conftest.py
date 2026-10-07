"""Shared fixtures for the hermetic suite (constitution Project structure #10).

Shared fixtures only: ``src/`` reaches the import path through ``pyproject.toml``'s
``[tool.pytest.ini_options] pythonpath``, never through ``sys.path`` edits here.
"""
