"""
Lote 5 — D-18 FECHADA: `co_buyers` tem UM significado (os compradores ADICIONAIS).

O DEFEITO
  O mapeador do CPCV gravava TODOS os compradores (o elemento 0 era o titular 1) e o `add-client` só os
  ADICIONAIS. Contar elementos dava resultados diferentes conforme quem escreveu o array; o titular 1
  aparecia como «titular adicional» no cartão do 2.º titular.

O QUE SE AFIRMA
  1. o mapeador REAL já não grava o titular 1 em `co_buyers` (e os dados dele continuam a ir para o
     `personal_data`);
  2. o classificador prova — por identidade exacta — se o elemento 0 de um documento antigo é o titular
     1, e na dúvida NÃO toca; um elemento do add-client nunca é retirado;
  3. o script migra só o provado, é condicional ao array lido, idempotente e deixa rasto;
  4. a regra Sub35 dá o MESMO veredicto antes e depois da migração (a desduplicação continua a servir
     os documentos ainda por migrar).
"""
from __future__ import annotations

import copy
from datetime import date

import pytest

from services import co_buyers_migration as mig
from services.sub35 import processo_e_sub35

HOJE = date(2026, 10, 14)

TITULAR_1 = {"nome": "Ana Costa", "nif": "234567890", "data_nascimento": "1995-04-01"}
SEGUNDO = {"nome": "Rui Santos", "nif": "345678901", "data_nascimento": "1993-02-02"}


def _processo(co_buyers, **extra):
    base = {
        "id": "p1", "client_name": "Ana Costa",
        "personal_data": {"nif": "234567890", "data_nascimento": "1995-04-01"},
        "co_buyers": co_buyers,
    }
    base.update(extra)
    return base


# ════════════════════════════════════════════════════════════════════
class TestOMapeadorNovo:
    def _extrair(self, compradores):
        from services.ai_document import build_update_data_from_extraction

        extracted = {"cpcv": {"compradores": compradores}}
        return build_update_data_from_extraction(extracted, "cpcv", {})

    def test_um_so_comprador_nao_grava_co_buyers(self):
        update = self._extrair([TITULAR_1])
        assert "co_buyers" not in update
        assert update["personal_data"]["nif"] == "234567890", "os dados do titular 1 continuam a ir para o personal_data"

    def test_dois_compradores_gravam_so_o_segundo(self):
        update = self._extrair([TITULAR_1, SEGUNDO])
        assert [c["nome"] for c in update["co_buyers"]] == ["Rui Santos"]
        assert update["personal_data"]["nif"] == "234567890"

    def test_tres_compradores_gravam_os_dois_adicionais_pela_ordem(self):
        terceiro = {"nome": "Eva Lima", "nif": "111222333"}
        update = self._extrair([TITULAR_1, SEGUNDO, terceiro])
        assert [c["nome"] for c in update["co_buyers"]] == ["Rui Santos", "Eva Lima"]


# ════════════════════════════════════════════════════════════════════
class TestOClassificador:
    def test_o_elemento_0_com_a_identidade_do_titular_1_e_migravel(self):
        assert mig.classificar(_processo([TITULAR_1, SEGUNDO])) == mig.VEREDICTO_RETIRAR_O_TITULAR_1

    def test_a_prova_pode_ser_so_o_nif(self):
        sem_nome = {"nif": "234567890", "data_nascimento": "1995-04-01"}
        assert mig.classificar(_processo([sem_nome])) == mig.VEREDICTO_RETIRAR_O_TITULAR_1

    def test_a_prova_pode_ser_so_o_nome_sem_acentos_nem_maiusculas_nem_espacos_a_mais(self):
        assert mig.classificar(_processo([{"nome": "  ANA   cóstá "}], personal_data={})) == mig.VEREDICTO_RETIRAR_O_TITULAR_1

    def test_mas_um_nome_parecido_nao_prova_nada(self):
        """Comparação EXACTA depois de normalizada: nada de scores de similaridade."""
        assert mig.classificar(_processo([{"nome": "Ana Costas"}], personal_data={})) == mig.VEREDICTO_AMBIGUO

    def test_a_exploracao_um_elemento_do_add_client_nunca_se_retira(self):
        """O titular 2 do add-client pode ter o mesmo nome do titular 1 (homónimos) — leva `client_id`/`relacao`."""
        do_add_client = {"name": "Ana Costa", "nif": "234567890", "client_id": "c2", "relacao": "co-titular"}
        assert mig.classificar(_processo([do_add_client])) == mig.VEREDICTO_JA_ADICIONAIS

    def test_um_adicional_do_mapeador_novo_nao_e_o_titular_1(self):
        """Um documento JÁ migrado (ou escrito pelo mapeador novo): o elemento 0 é outra pessoa."""
        assert mig.classificar(_processo([SEGUNDO])) == mig.VEREDICTO_AMBIGUO
        # ...e é por isso que a segunda passagem não toca em nada: ver `TestOScript.test_idempotente`.

    def test_na_duvida_nao_toca(self):
        outro_nome = {"nome": "Ana C. Costa Silva", "nif": "999888777"}
        assert mig.classificar(_processo([outro_nome])) == mig.VEREDICTO_AMBIGUO

    @pytest.mark.parametrize("doc", [None, {}, {"co_buyers": None}, {"co_buyers": []}, {"co_buyers": "x"}])
    def test_sem_co_buyers_nao_ha_nada_a_fazer(self, doc):
        assert mig.classificar(doc) == mig.VEREDICTO_SEM_CO_BUYERS

    def test_elemento_que_nao_e_um_dicionario_e_ambiguo(self):
        assert mig.classificar(_processo(["lixo"])) == mig.VEREDICTO_AMBIGUO

    def test_o_titular_2_nao_prova_que_o_elemento_0_e_o_titular_1(self):
        """Só o titular 1 conta: um elemento igual ao `titular2_data` não é duplicado do titular 1."""
        doc = _processo([{"nome": "Rui Santos", "nif": "345678901"}], titular2_data={"name": "Rui Santos", "nif": "345678901"})
        assert mig.classificar(doc) == mig.VEREDICTO_AMBIGUO

    def test_sem_o_primeiro(self):
        assert mig.sem_o_primeiro([1, 2, 3]) == [2, 3]
        assert mig.sem_o_primeiro([1]) is None


# ════════════════════════════════════════════════════════════════════
class _Db:
    def __init__(self, fake):
        self.processes = fake.processes
        self.audit_logs = fake.audit_logs


@pytest.mark.asyncio
class TestOScript:
    @pytest.fixture
    def migrar(self, fake_async_db):
        import importlib.util
        import pathlib

        caminho = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "migrar_co_buyers_adicionais.py"
        spec = importlib.util.spec_from_file_location("migrar_co_buyers_adicionais", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo.migrar, fake_async_db

    def _semear(self, bd):
        bd.processes.docs.extend([
            _processo([dict(TITULAR_1), dict(SEGUNDO)], id="p-migravel"),
            _processo([dict(TITULAR_1)], id="p-so-titular"),
            _processo([dict(SEGUNDO)], id="p-ambiguo"),
            _processo([{"name": "Ana Costa", "client_id": "c2", "relacao": "co-titular"}], id="p-add-client"),
            _processo(None, id="p-sem"),
        ])

    async def test_a_omissao_le_e_conta_e_nao_escreve(self, migrar):
        funcao, bd = migrar
        self._semear(bd)
        antes = copy.deepcopy(bd.processes.docs)
        r = await funcao(bd, aplicar=False)
        assert bd.processes.docs == antes
        assert r["resumo"][mig.VEREDICTO_RETIRAR_O_TITULAR_1] == 2
        assert r["resumo"][mig.VEREDICTO_AMBIGUO] == 1
        assert r["resumo"][mig.VEREDICTO_JA_ADICIONAIS] == 1
        assert bd.audit_logs.docs == []

    async def test_aplicar_migra_so_o_provado(self, migrar):
        funcao, bd = migrar
        self._semear(bd)
        await funcao(bd, aplicar=True)
        por_id = {p["id"]: p for p in bd.processes.docs}
        assert [c["nome"] for c in por_id["p-migravel"]["co_buyers"]] == ["Rui Santos"]
        assert "co_buyers" not in por_id["p-so-titular"], "sem adicionais o campo desaparece"
        assert por_id["p-ambiguo"]["co_buyers"] == [SEGUNDO], "o ambíguo NUNCA é tocado"
        assert por_id["p-add-client"]["co_buyers"][0]["client_id"] == "c2"

    async def test_idempotente(self, migrar):
        funcao, bd = migrar
        self._semear(bd)
        await funcao(bd, aplicar=True)
        depois_da_primeira = copy.deepcopy(bd.processes.docs)
        r = await funcao(bd, aplicar=True)
        assert bd.processes.docs == depois_da_primeira
        assert r["resumo"][mig.VEREDICTO_RETIRAR_O_TITULAR_1] == 0

    async def test_edicao_concorrente_nao_e_pisada(self, migrar):
        funcao, bd = migrar
        self._semear(bd)
        original = bd.processes.update_one

        async def com_edicao(filtro, operacao, *a, **k):
            if filtro.get("id") == "p-migravel":  # alguém acrescentou um comprador entre a leitura e a escrita
                next(p for p in bd.processes.docs if p["id"] == "p-migravel")["co_buyers"].append({"nome": "Novo"})
            return await original(filtro, operacao, *a, **k)

        bd.processes.update_one = com_edicao
        r = await funcao(bd, aplicar=True)
        migravel = next(x for x in r["registos"] if x["id"] == "p-migravel")
        assert migravel["estado"] == "inalterado"
        assert len(next(p for p in bd.processes.docs if p["id"] == "p-migravel")["co_buyers"]) == 3

    async def test_deixa_rasto_so_quando_gravou(self, migrar):
        funcao, bd = migrar
        self._semear(bd)
        await funcao(bd, aplicar=True)
        assert len(bd.audit_logs.docs) == 1
        assert sorted(bd.audit_logs.docs[0]["metadata"]["processos"]) == ["p-migravel", "p-so-titular"]
        await funcao(bd, aplicar=True)
        assert len(bd.audit_logs.docs) == 1, "uma passagem que não grava não deixa rasto"


# ════════════════════════════════════════════════════════════════════
class TestASub35DaOMesmoVeredictoAntesEDepois:
    """A desduplicação por identidade continua a servir os documentos ainda por migrar."""

    @pytest.mark.parametrize("compradores", [
        [TITULAR_1],                       # um só comprador
        [TITULAR_1, SEGUNDO],              # dois, ambos sub35
        [TITULAR_1, {"nome": "Velho", "nif": "555", "data_nascimento": "1970-01-01"}],  # o 2.º bloqueia
    ])
    def test_antes_e_depois(self, compradores):
        antes = _processo(copy.deepcopy(compradores))
        depois = _processo(mig.sem_o_primeiro(copy.deepcopy(compradores)))
        if depois["co_buyers"] is None:
            depois.pop("co_buyers")
        assert processo_e_sub35(antes, HOJE) == processo_e_sub35(depois, HOJE)
