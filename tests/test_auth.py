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


def test_is_worker_never_raises_and_fails_closed(monkeypatch):
    """/ask is open to the internet and must keep answering strangers, so
    this one returns a verdict instead of refusing. It still fails closed."""
    monkeypatch.delenv("WORKER_TOKEN", raising=False)
    assert auth.is_worker("anything") is False, "no token configured trusts nobody"

    monkeypatch.setenv("WORKER_TOKEN", "the-real-secret")
    assert auth.is_worker("the-real-secret") is True
    assert auth.is_worker("  the-real-secret  ") is True
    assert auth.is_worker("wrong") is False
    assert auth.is_worker("") is False
    assert auth.is_worker() is False


def test_a_valid_call_records_when_the_worker_last_spoke(monkeypatch):
    """The API cannot see whether WhatsApp still talks to the bot, but it can
    see whether the bot still talks to the API. Four logouts in eighteen
    hours were each found by somebody noticing the bot had gone quiet, hours
    later. /health reports this so a check can find it first."""
    monkeypatch.setenv("WORKER_TOKEN", "the-real-secret")
    monkeypatch.setattr(auth, "last_worker_call", None)

    auth.require_worker("the-real-secret")

    assert auth.last_worker_call is not None


def test_a_refused_call_does_not_count(monkeypatch):
    """Otherwise anybody probing the endpoint from the internet would keep
    the liveness figure looking healthy while the worker was dead."""
    monkeypatch.setenv("WORKER_TOKEN", "the-real-secret")
    monkeypatch.setattr(auth, "last_worker_call", None)

    with pytest.raises(HTTPException):
        auth.require_worker("wrong")

    assert auth.last_worker_call is None
