"""Shared pytest plumbing for the Python suites.

Many suites chdir into a temp directory (GameState reads and writes games.json
in the working directory), some per test and some once per class, and a
failing setUp can leave the process wherever it was. Every test MODULE starts
and ends in the repo root, so one suite's directory can never become the next
one's — that is how `survivor_cards.json` copies went missing across suites in
a single pytest run. Module scope leaves each suite's own chdir alone.
"""
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True, scope="module")
def _repo_root_cwd():
    os.chdir(REPO_ROOT)
    yield
    os.chdir(REPO_ROOT)
