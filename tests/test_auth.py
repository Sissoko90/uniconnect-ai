"""Which endpoints are public, and which are not.

Found by a security review of what had just been pushed, not by us. `/alerts`
says who was named in a private group and quotes what was said to them, and
our own nginx configuration proxied the entire API - so the day we deployed,
that would have been on the open internet.

These tests exist so that the next endpoint somebody adds has to decide
consciously which side of the line it is on.
"""

import auth
import pytest
from fastapi import HTTPException


def test_an_unset_token_disables_rather_than_opens(monkeypatch):
    """The failure that matters. An unset secret must never mean "no check" -
    that is how a private group ends up being served to anybody who guesses a
    group id."""
    monkeypatch.delenv("WORKER_TOKEN", raising=False)

    with pytest.raises(HTTPException) as raised:
        auth.require_worker("anything")

    assert raised.value.status_code == 503
    assert "WORKER_TOKEN" in raised.value.detail


def test_a_wrong_token_is_refused(monkeypatch):
    monkeypatch.setenv("WORKER_TOKEN", "the-real-secret")

    with pytest.raises(HTTPException) as raised:
        auth.require_worker("not-the-secret")

    assert raised.value.status_code == 401


def test_a_missing_header_is_refused(monkeypatch):
    monkeypatch.setenv("WORKER_TOKEN", "the-real-secret")

    with pytest.raises(HTTPException):
        auth.require_worker()


def test_the_right_token_passes(monkeypatch):
    monkeypatch.setenv("WORKER_TOKEN", "the-real-secret")

    assert auth.require_worker("the-real-secret") is None
    # Whitespace from a shell variable or a copy-paste is not a wrong token.
    assert auth.require_worker("  the-real-secret  ") is None


def test_configured_reports_the_truth(monkeypatch):
    """/health surfaces this, so a deploy that forgot the token says so
    instead of silently refusing everything the worker sends."""
    monkeypatch.delenv("WORKER_TOKEN", raising=False)
    assert auth.configured() is False

    monkeypatch.setenv("WORKER_TOKEN", "   ")
    assert auth.configured() is False, "whitespace is not a token"

    monkeypatch.setenv("WORKER_TOKEN", "x")
    assert auth.configured() is True
