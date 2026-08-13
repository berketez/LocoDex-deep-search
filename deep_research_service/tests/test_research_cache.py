"""
Önbellek katmanı testleri.

Ana davranışlar: anahtar motor + modeli içerir (farklı modelin cevabı
dönmez), /yeni önbelleği atlar ama sonucu tazeler, kaynaksız biten koşu
önbelleğe yazılmaz.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cli  # noqa: E402
from utils.research_cache import ResearchCache  # noqa: E402


class TestVaryantAnahtari:
    def test_farkli_model_veya_motor_ayri_kayittir(self, tmp_path):
        cache = ResearchCache(db_path=str(tmp_path / "cache.db"))
        cache.set("konu", {"answer": "gemma cevabı"}, "verified|gemma4:31b")

        assert cache.get("konu", "verified|gemma4:31b") == {"answer": "gemma cevabı"}
        assert cache.get("konu", "verified|qwen3.6") is None
        assert cache.get("konu", "smart|gemma4:31b") is None
        assert cache.get("konu") is None

    def test_silme_varyanta_gore(self, tmp_path):
        cache = ResearchCache(db_path=str(tmp_path / "cache.db"))
        cache.set("konu", {"answer": "a"}, "verified|m1")
        cache.set("konu", {"answer": "b"}, "verified|m2")
        cache.delete("konu", "verified|m1")
        assert cache.get("konu", "verified|m1") is None
        assert cache.get("konu", "verified|m2") == {"answer": "b"}


# ----------------------------------------------------------------------
# CLI akışı: _execute_research önbellek davranışı
# ----------------------------------------------------------------------

class SahteCache:
    def __init__(self):
        self.store = {}
        self.set_calls = []

    def get(self, topic, variant=""):
        return self.store.get((topic, variant))

    def set(self, topic, result, variant=""):
        self.set_calls.append((topic, variant))
        self.store[(topic, variant)] = result


class SahteMotor:
    """Kaynak bulan sahte araştırma motoru."""

    kaynaklar = [{"url": "https://example.com", "domain": "example.com"}]

    def __init__(self, model_name, model_source, websocket):
        self.sources = list(self.kaynaklar)
        self.findings = []
        self.skipped = {}
        self.all_queries = []

    async def run_research(self, topic):
        return "# Taze Rapor"


class SahteKaynaksizMotor(SahteMotor):
    kaynaklar = []


def _args():
    return argparse.Namespace(
        engine="verified", out=None, no_cache=False, quiet=True,
        sources=None, rounds=None, queries=None,
    )


def _kos(monkeypatch, motor, cache, force_fresh):
    monkeypatch.setattr(cli, "_prepare_engine", lambda args, style: (motor, cache))
    style = cli.Style(False)
    return cli._execute_research("konu", "m1", "Ollama", _args(), style,
                                 force_fresh=force_fresh)


class TestCliOnbellekAkisi:
    def test_kayit_varsa_onbellekten_doner(self, monkeypatch):
        cache = SahteCache()
        cache.store[("konu", "verified|m1")] = {"answer": "eski rapor"}
        sonuc = _kos(monkeypatch, SahteMotor, cache, force_fresh=False)
        assert sonuc.from_cache
        assert sonuc.report == "eski rapor"

    def test_yeni_komutu_onbellegi_atlar_ve_tazeler(self, monkeypatch):
        # /yeni yolu: kayıt VARKEN bile araştırma baştan koşmalı; önceki
        # davranışta aynı öneri mesajı sonsuza kadar dönüyordu.
        cache = SahteCache()
        cache.store[("konu", "verified|m1")] = {"answer": "eski rapor"}
        sonuc = _kos(monkeypatch, SahteMotor, cache, force_fresh=True)
        assert not sonuc.from_cache
        assert sonuc.report == "# Taze Rapor"
        assert cache.store[("konu", "verified|m1")]["answer"] == "# Taze Rapor"

    def test_kaynaksiz_kosu_onbellege_yazilmaz(self, monkeypatch):
        cache = SahteCache()
        sonuc = _kos(monkeypatch, SahteKaynaksizMotor, cache, force_fresh=False)
        assert sonuc.report == "# Taze Rapor"
        assert cache.set_calls == []

    def test_kaynakli_kosu_onbellege_yazilir(self, monkeypatch):
        cache = SahteCache()
        _kos(monkeypatch, SahteMotor, cache, force_fresh=False)
        assert cache.set_calls == [("konu", "verified|m1")]
