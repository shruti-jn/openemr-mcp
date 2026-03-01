"""Pytest configuration — force mock mode for all tests."""
import os

import pytest


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Ensure all tests run in mock mode with no external API calls."""
    monkeypatch.setenv("OPENEMR_DATA_SOURCE", "mock")
    monkeypatch.setenv("DRUG_INTERACTION_SOURCE", "mock")
    monkeypatch.setenv("SYMPTOM_SOURCE", "mock")
    monkeypatch.setenv("OPENFDA_SOURCE", "mock")
