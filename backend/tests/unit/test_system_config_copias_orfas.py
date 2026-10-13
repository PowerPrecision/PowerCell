"""Cópias órfãs de ``system_config`` (``company:<id>``): classificação e copy-on-write.

Duas metades da mesma correcção — **código primeiro**: de nada servia apagar as
cópias enquanto a leitura continuasse a gravá-las.
"""
from __future__ import annotations

import copy

import pytest

from models.system_config import SystemConfig
from services import system_config_orphans as orf


def _global(**extra) -> dict:
    doc = SystemConfig(company_id="default").model_dump(mode="json")
    doc["_id"] = "main"
    doc["email"]["smtp_user"] = "geral@power.pt"
    doc["email"]["smtp_password"] = "SEGREDO-DA-GLOBAL"
    doc["setup_completed"] = True
    doc.update(extra)
    return doc


def _copia(empresa: str, glob: dict, **mudancas) -> dict:
    doc = copy.deepcopy(glob)
    doc["_id"] = f"company:{empresa}"
    doc["company_id"] = empresa
    doc["setup_completed"] = False  # a cópia nunca herda a flag
    doc["created_at"] = "2026-09-01T10:00:00+00:00"
    doc["updated_at"] = "2026-09-01T10:00:00+00:00"
    for caminho, valor in mudancas.items():
        seccao, _, campo = caminho.partition(".")
        if campo:
            doc[seccao][campo] = valor
        else:
            doc[seccao] = valor
    return doc


class TestClassificar:
    def test_uma_copia_exacta_e_identica_mesmo_com_campos_volateis_diferentes(self):
        g = _global()
        [v] = orf.classificar_todas([_copia("cmp-a", g)], g, {"cmp-a"})
        assert v.veredicto == orf.VEREDICTO_IDENTICA and v.apagavel_por_omissao

    def test_qualquer_diferenca_numa_seccao_torna_a_copia_divergente(self):
        g = _global()
        for caminho, valor in [("email.smtp_user", "domus@domus.pt"), ("ai.model", "outro"),
                               ("settings.company_name", "Domus")]:
            [v] = orf.classificar_todas([_copia("cmp-a", g, **{caminho: valor})], g, {"cmp-a"})
            assert v.veredicto == orf.VEREDICTO_DIVERGENTE, caminho
            assert not v.apagavel_por_omissao
            assert caminho.split(".")[0] in v.seccoes_diferentes

    def test_o_relatorio_nunca_leva_valores(self):
        g = _global()
        [v] = orf.classificar_todas([_copia("cmp-a", g, **{"email.smtp_password": "OUTRO-SEGREDO"})], g, {"cmp-a"})
        assert "SEGREDO" not in repr(v)

    def test_copia_de_empresa_inexistente_nao_e_apagavel_por_omissao(self):
        g = _global()
        [v] = orf.classificar_todas([_copia("cmp-fantasma", g)], g, {"cmp-a"})
        assert v.veredicto == orf.VEREDICTO_SEM_EMPRESA and not v.apagavel_por_omissao
        assert orf.a_apagar([v]) == []
        assert orf.a_apagar([v], incluir_sem_empresa=True) == [v]

    def test_uma_global_antiga_sem_campos_novos_nao_faz_a_copia_parecer_divergente(self):
        g = _global()
        antiga = copy.deepcopy(g)
        antiga.pop("dashboard_slas")
        antiga.pop("financial_simulator")
        [v] = orf.classificar_todas([_copia("cmp-a", g)], antiga, {"cmp-a"})
        assert v.veredicto == orf.VEREDICTO_IDENTICA

    def test_documento_que_nao_valida_e_ilegivel(self):
        g = _global()
        mau = _copia("cmp-a", g)
        mau["email"] = "isto não é um bloco de email"
        [v] = orf.classificar_todas([mau], g, {"cmp-a"})
        assert v.veredicto == orf.VEREDICTO_ILEGIVEL and not v.apagavel_por_omissao

    def test_so_se_classificam_documentos_company(self):
        g = _global()
        outros = [
            {"_id": "main"}, {"_id": "rgpd_template"}, {"_id": "minuta_template"},
            {"_id": "finance_config"}, {"_id": "company:"}, {"_id": 123}, {"type": "cache_settings"},
        ]
        assert orf.classificar_todas(outros, g, set()) == []

    def test_sem_global_nada_se_classifica(self):
        for sem in (None, {}, {"email": "lixo"}):
            with pytest.raises(orf.ConfiguracaoGlobalIlegivel):
                orf.classificar_todas([_copia("cmp-a", _global())], sem, {"cmp-a"})

    def test_resumo_conta_por_veredicto(self):
        g = _global()
        docs = [_copia("a", g), _copia("b", g), _copia("c", g, **{"ai.model": "x"})]
        r = orf.resumir(orf.classificar_todas(docs, g, {"a", "b", "c"}))
        assert r.total == 3
        assert r.por_veredicto == {orf.VEREDICTO_IDENTICA: 2, orf.VEREDICTO_DIVERGENTE: 1}


@pytest.mark.asyncio
class TestLerNaoGrava:
    """Copy-on-write: a torneira fechada. Sem isto, limpar a base de dados era
    esfregar o chão com a torneira aberta."""

    @pytest.fixture
    def cfg(self, fake_async_db, monkeypatch):
        import services.system_config as sc

        monkeypatch.setattr(sc, "db", fake_async_db)
        sc._config_cache.clear()
        fake_async_db.system_config.docs.append(_global())
        yield sc, fake_async_db
        sc._config_cache.clear()

    async def test_ler_a_config_de_uma_empresa_sem_config_propria_nao_grava_nada(self, cfg):
        sc, bd = cfg
        config = await sc.get_system_config("cmp-nova")
        assert config.company_id == "cmp-nova"
        assert config.email.smtp_user == "geral@power.pt", "continua a herdar em memória"
        assert [d["_id"] for d in bd.system_config.docs] == ["main"]

    async def test_a_primeira_escrita_cria_o_documento_da_empresa(self, cfg):
        sc, bd = cfg
        await sc.update_config_section("settings", {"company_name": "Domus"}, "cmp-nova")
        ids = [d["_id"] for d in bd.system_config.docs]
        assert ids == ["main", "company:cmp-nova"]
        propria = next(d for d in bd.system_config.docs if d["_id"] == "company:cmp-nova")
        assert propria["settings"]["company_name"] == "Domus"
        assert propria["company_id"] == "cmp-nova"

    async def test_depois_de_escrever_a_leitura_devolve_a_propria(self, cfg):
        sc, _ = cfg
        await sc.update_config_section("settings", {"company_name": "Domus"}, "cmp-nova")
        sc._config_cache.clear()
        assert (await sc.get_system_config("cmp-nova")).settings.company_name == "Domus"

    async def test_contraprova_a_global_continua_a_criar_se_nao_existir(self, fake_async_db, monkeypatch):
        import services.system_config as sc

        monkeypatch.setattr(sc, "db", fake_async_db)
        sc._config_cache.clear()
        await sc.get_system_config("default")
        assert [d["_id"] for d in fake_async_db.system_config.docs] == ["main"]
        sc._config_cache.clear()
