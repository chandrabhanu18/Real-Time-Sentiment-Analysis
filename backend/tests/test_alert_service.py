import asyncio
import os
import pytest

from backend.services.alerting import AlertService


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        return FakeResult(self._rows)


def make_session_maker(rows):
    def maker():
        return FakeSession(rows)

    return maker


@pytest.mark.asyncio
async def test_no_alert_when_insufficient_posts():
    # fewer posts than min_posts -> no alert
    rows = []
    svc = AlertService(make_session_maker(rows))
    svc.min_posts = 5
    res = await svc.check_thresholds()
    assert res is None


@pytest.mark.asyncio
async def test_alert_triggered_on_high_negative_ratio():
    class R:
        def __init__(self, label):
            self.sentiment_label = label

    # 1 positive, 10 negative -> ratio 10 -> alert
    rows = [R('positive')] + [R('negative')] * 10 + [R('neutral')] * 2
    svc = AlertService(make_session_maker(rows))
    svc.min_posts = 1
    svc.threshold = 2.0
    alert = await svc.check_thresholds()
    assert alert is not None
    assert alert['alert_triggered'] is True
    assert alert['alert_type'] == 'high_negative_ratio'
