"""Adım süre telemetrisi testleri — ölçüm gerçek monotonic saatten gelir."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verified_research import VerifiedDeepResearcher  # noqa: E402


def _motor():
    return VerifiedDeepResearcher("m", "Ollama", None)


def test_sure_ayni_asamada_birikir():
    motor = _motor()
    t0 = time.monotonic() - 1.0  # 1 sn önce başlamış gibi
    motor._sure_kaydet("analiz", t0)
    motor._sure_kaydet("analiz", time.monotonic() - 0.5)
    assert 1.4 <= motor.timings["analiz"] <= 1.7


def test_donen_deger_yeni_baslangic():
    motor = _motor()
    yeni_t = motor._sure_kaydet("arama", time.monotonic())
    assert abs(time.monotonic() - yeni_t) < 0.05
    assert "arama" in motor.timings


def test_timings_bos_baslar():
    assert _motor().timings == {}
