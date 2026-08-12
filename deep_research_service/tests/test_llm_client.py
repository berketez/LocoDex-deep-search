"""
LLM çıktısından JSON kurtarma testleri.

Yerel modeller token limitine takıldığında JSON'u yarıda kesiyor. Tamamlanmış
elemanların kurtarılması, araştırma turunun tamamen boşa gitmesini önler.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_client import _repair_truncated, extract_json  # noqa: E402


class TestExtractJsonTam:
    def test_duz_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_markdown_citi_soyulur(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_metin_icine_gomulu(self):
        assert extract_json('İşte sonuç: {"a": 1} umarım yardımcı olur') == {"a": 1}

    def test_sondaki_gereksiz_virgul(self):
        assert extract_json('{"liste": [1, 2,]}') == {"liste": [1, 2]}

    def test_dizi_kok(self):
        assert extract_json("[1, 2, 3]") == [1, 2, 3]

    def test_bos_girdi(self):
        assert extract_json("") is None
        assert extract_json(None) is None

    def test_json_olmayan_metin(self):
        assert extract_json("burada hiç JSON yok") is None


class TestKesikJsonKurtarma:
    def test_nesne_ortasinda_kesilmis(self):
        ham = '{"bulgular": [{"ifade": "A", "destek": [1]}, {"ifade": "B", "des'
        sonuc = extract_json(ham)
        assert sonuc is not None
        assert len(sonuc["bulgular"]) == 1
        assert sonuc["bulgular"][0]["ifade"] == "A"

    def test_string_ortasinda_kesilmis(self):
        ham = '{"bulgular": [{"ifade": "A"}, {"ifade": "yarım kalan uzun met'
        sonuc = extract_json(ham)
        assert len(sonuc["bulgular"]) == 1

    def test_tek_tam_elemandan_sonra_kesilmis(self):
        ham = '{"bulgular": [{"ifade": "A", "destek": [1]}'
        sonuc = extract_json(ham)
        assert len(sonuc["bulgular"]) == 1

    def test_birden_fazla_tam_eleman_korunur(self):
        ham = '{"b": [{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4'
        sonuc = extract_json(ham)
        assert [e["x"] for e in sonuc["b"]] == [1, 2, 3]

    def test_hic_tam_eleman_yoksa_none(self):
        assert extract_json('{"bulgular": [{"ifade": "yarım') is None

    def test_string_icindeki_parantez_yanilmaz(self):
        ham = '{"b": [{"x": "içinde } ve ] var"}, {"x": "kesik'
        sonuc = extract_json(ham)
        assert len(sonuc["b"]) == 1
        assert sonuc["b"][0]["x"] == "içinde } ve ] var"

    def test_kacisli_tirnak_yanilmaz(self):
        ham = '{"b": [{"x": "tırnak \\" içeride"}, {"x": "kes'
        sonuc = extract_json(ham)
        assert len(sonuc["b"]) == 1


class TestRepairTruncated:
    def test_kurtarilacak_sey_yoksa_none(self):
        assert _repair_truncated("düz metin") is None

    def test_tam_json_dokunulmadan_gecer(self):
        onarilmis = _repair_truncated('{"b": [{"x": 1}]}')
        assert onarilmis is not None
        assert "{" in onarilmis

    def test_ic_ice_dizi_kapatilir(self):
        ham = '{"b": [{"x": [1, 2]}, {"y": [3'
        onarilmis = _repair_truncated(ham)
        assert onarilmis.endswith("}")
