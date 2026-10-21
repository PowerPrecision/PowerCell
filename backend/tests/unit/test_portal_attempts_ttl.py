"""D-31 (remate) — `portal_verify_attempts` e `portal_login_attempts` deixam de crescer para sempre.

O DEFEITO
=========
O travão do `POST /portal/{client_id}/verify` guarda um documento por
`client_id` falhado, e o `client_id` é escolhido por quem pergunta: cada id
inventado deixava um registo que nunca expirava. Não é uma fuga entre redes
(o 401 é igual para tudo), é crescimento sem fim de uma colecção pública.

O QUE SE AFIRMA
===============
* o escritor grava `expire_at` como **datetime nativo** (o TTL do Mongo ignora
  uma string ISO) e **desliza** a cada falha;
* o prazo é **maior que o bloqueio** — medido no escritor real, após as cinco
  falhas: um TTL curto desbloqueava o alvo a meio;
* o índice está declarado em `db_indexes` sobre ESSE campo, com `expireAfterSeconds`
  igual a **0** (zero é um valor: um `if valor:` descartava-o e criava um índice
  normal, sem purga) — afirmado ao nível da chamada ao driver;
* os registos antigos têm uma data a gravar que nunca desbloqueia quem está
  bloqueado agora;
* **as duas portas do Portal** (NIF e email) partilham o campo, o prazo e o
  backfill — duas políticas no mesmo ecrã de entrada é a divergência da D-4.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services import db_indexes, portal_brute_force, portal_security
from services.portal_attempts_ttl import COLECCOES_DE_TENTATIVAS, expire_at_do_registo

AGORA = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
CLIENTE = "cli-inventado"
CHAVE = f"portal_verify:{CLIENTE}"


def _indice_do_login() -> dict:
    achados = [i for i in db_indexes.TTL_INDEXES if i["name"] == "ttl_portal_login_attempts"]
    assert len(achados) == 1
    return achados[0]


def _indice() -> dict:
    achados = [i for i in db_indexes.TTL_INDEXES if i["name"] == "ttl_portal_verify_attempts"]
    assert len(achados) == 1
    return achados[0]


async def _falhar(bd):
    """Uma falha do `verify`, no escritor REAL (o ponto único `portal_brute_force`)."""
    await portal_brute_force.registar_falha(bd, portal_brute_force.AMBITO_DO_VERIFY, CLIENTE)


@pytest.fixture
def tentativas(fake_async_db):
    with patch.object(portal_security, "db", fake_async_db):
        yield fake_async_db.portal_verify_attempts


# ════════════════════════════════════════════════════════════════════
class TestOEscritorGravaUmaDataQueOTTLEntende:
    @pytest.mark.asyncio
    async def test_expire_at_e_um_datetime_nativo_e_nao_um_texto(self, tentativas, fake_async_db):
        await _falhar(fake_async_db)

        doc = await tentativas.find_one({"_id": CHAVE})
        campo = _indice()["field"]                      # o campo vem do ÍNDICE
        assert isinstance(doc[campo], datetime), type(doc[campo])
        assert isinstance(doc["last_attempt_at"], str)  # o texto antigo fica como está

    @pytest.mark.asyncio
    async def test_expira_30_minutos_depois_da_falha(self, tentativas, fake_async_db):
        antes = datetime.now(timezone.utc)
        await _falhar(fake_async_db)
        depois = datetime.now(timezone.utc)

        expira = (await tentativas.find_one({"_id": CHAVE}))["expire_at"]
        expira = expira if expira.tzinfo else expira.replace(tzinfo=timezone.utc)
        assert antes + timedelta(minutes=30) <= expira <= depois + timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_cada_nova_falha_desliza_o_prazo(self, tentativas, fake_async_db):
        """Um ataque em curso não pode ver o contador voltar a zero a meio."""
        await tentativas.insert_one({
            "_id": CHAVE, "attempts": 1,
            "expire_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        })
        await _falhar(fake_async_db)

        doc = await tentativas.find_one({"_id": CHAVE})
        assert doc["attempts"] == 2
        assert doc["expire_at"].replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_o_registo_sobrevive_ao_bloqueio_inteiro(self, tentativas, fake_async_db):
        """Medido no escritor REAL, depois das cinco falhas: o registo (e com
        ele o bloqueio) vive para além de `locked_until`."""
        for _ in range(portal_security.MAX_VERIFY_ATTEMPTS):
            await _falhar(fake_async_db)

        doc = await tentativas.find_one({"_id": CHAVE})
        bloqueado_ate = datetime.fromisoformat(doc["locked_until"])
        assert doc["expire_at"].replace(tzinfo=timezone.utc) > bloqueado_ate
        assert doc["expire_at"].replace(tzinfo=timezone.utc) - bloqueado_ate >= timedelta(minutes=10)

    def test_o_prazo_e_maior_que_o_bloqueio(self):
        assert portal_security.VERIFY_ATTEMPTS_TTL_MINUTES > portal_security.VERIFY_LOCKOUT_MINUTES
        assert portal_security.VERIFY_ATTEMPTS_TTL_MINUTES == 30

    @pytest.mark.asyncio
    async def test_um_bloqueio_expirado_deixa_de_prender_o_cliente(self, tentativas, fake_async_db):
        """Antes, `attempts >= 5` re-trancava o cliente a cada pedido, para sempre
        (o 429 vinha ANTES de qualquer credencial). Com o registo purgado pelo
        TTL, o pedido segue para a verificação normal."""
        for _ in range(portal_security.MAX_VERIFY_ATTEMPTS):
            await _falhar(fake_async_db)
        await tentativas.delete_one({"_id": CHAVE})           # o que o TTL faz

        with patch.object(portal_security, "db") as bd:
            bd.portal_verify_attempts = tentativas
            bd.clients = type("C", (), {"find_one": staticmethod(_nenhum)})()
            with pytest.raises(Exception) as erro:
                await portal_security.verify_client_credentials("cli-inventado", "123456789", "1")
        assert getattr(erro.value, "status_code", None) == 401      # e não 429


async def _nenhum(*_a, **_k):
    return None


# ════════════════════════════════════════════════════════════════════
class TestOIndiceEstaDeclaradoEChegaAoDriver:
    def test_declaracao(self):
        indice = _indice()
        assert indice["collection"] == "portal_verify_attempts"
        assert indice["field"] == "expire_at"
        assert indice["seconds"] == 0

    def test_o_login_por_email_tem_o_seu_indice_com_o_mesmo_campo(self):
        indice = _indice_do_login()
        assert indice["collection"] == "portal_login_attempts"
        assert indice["field"] == "expire_at"
        assert indice["seconds"] == 0

    def test_o_backfill_cobre_exactamente_as_colecoes_com_este_ttl(self):
        """Uma terceira colecção com TTL em `expire_at` e sem backfill deixava
        os registos antigos para sempre; uma de mais no backfill escrevia onde
        o TTL não actua."""
        # `process_ai_log` tem TTL em `expire_at` mas NÃO é uma colecção de tentativas
        # de login: nasceu já com datetime nativo em todas as linhas (`montar_linha`),
        # logo não há registos antigos (texto) a corrigir com o backfill.
        sem_backfill_por_desenho = {"process_ai_log"}
        com_ttl = {
            i["collection"] for i in db_indexes.TTL_INDEXES if i["field"] == "expire_at"
        } - sem_backfill_por_desenho
        assert set(COLECCOES_DE_TENTATIVAS) == com_ttl

    @pytest.mark.asyncio
    async def test_o_zero_chega_ao_create_index_do_driver(self):
        """`expireAfterSeconds=0` tem de ser ENVIADO: um `if valor:` descartava-o
        e o índice nascia normal, sem purga alguma — e sem erro."""
        chamadas: list[tuple] = []

        class Coleccao:
            async def index_information(self):
                return {}

            async def create_index(self, chaves, **opcoes):
                chamadas.append((chaves, opcoes))

            def __getattr__(self, nome):                 # drop_index, etc.
                async def _f(*_a, **_k):
                    return None
                return _f

        class BD:
            def __getitem__(self, nome):
                return Coleccao()

            def __getattr__(self, nome):
                return Coleccao()

        await db_indexes.create_ttl_indexes(BD())

        for nome in ("ttl_portal_verify_attempts", "ttl_portal_login_attempts"):
            proprio = [c for c in chamadas if c[1].get("name") == nome]
            assert len(proprio) == 1, nome
            chaves, opcoes = proprio[0]
            assert chaves == [("expire_at", 1)]
            assert "expireAfterSeconds" in opcoes and opcoes["expireAfterSeconds"] == 0

    def test_os_outros_ttl_nao_foram_tocados(self):
        por_nome = {i["name"]: i["seconds"] for i in db_indexes.TTL_INDEXES}
        assert por_nome["ttl_refresh_tokens"] == 86_400
        assert por_nome["ttl_task_queue"] == 604_800
        assert por_nome["ttl_email_drafts"] == db_indexes.RASCUNHOS_TTL_SEGUNDOS


# ════════════════════════════════════════════════════════════════════
class TestOBackfillDosRegistosAntigos:
    def test_parte_da_ultima_tentativa_e_nao_de_agora(self):
        antiga = (AGORA - timedelta(days=40)).isoformat()
        expira = expire_at_do_registo({"last_attempt_at": antiga}, agora=AGORA)
        assert expira == AGORA - timedelta(days=40) + timedelta(minutes=30)
        assert expira < AGORA                   # o TTL apaga-o na 1.ª passagem

    def test_sem_data_legivel_parte_de_agora(self):
        for doc in ({}, {"last_attempt_at": "lixo"}, {"last_attempt_at": None}):
            assert expire_at_do_registo(doc, agora=AGORA) == AGORA + timedelta(minutes=30)

    def test_nunca_desbloqueia_quem_esta_bloqueado_agora(self):
        doc = {
            "last_attempt_at": (AGORA - timedelta(days=40)).isoformat(),
            "locked_until": (AGORA + timedelta(minutes=10)).isoformat(),
        }
        assert expire_at_do_registo(doc, agora=AGORA) >= AGORA + timedelta(minutes=11)

    def test_um_bloqueio_ja_passado_nao_alarga_o_prazo(self):
        doc = {
            "last_attempt_at": (AGORA - timedelta(days=2)).isoformat(),
            "locked_until": (AGORA - timedelta(days=2) + timedelta(minutes=15)).isoformat(),
        }
        assert expire_at_do_registo(doc, agora=AGORA) < AGORA

    def test_datetimes_ingenuos_valem_como_utc(self):
        doc = {"last_attempt_at": datetime(2026, 10, 11, 11, 0, 0)}
        assert expire_at_do_registo(doc, agora=AGORA) == datetime(2026, 10, 11, 11, 30, tzinfo=timezone.utc)


class TestOScriptDeBackfill:
    @pytest.fixture
    def base(self, fake_async_db):
        fake_async_db.portal_login_attempts.docs.extend([
            {"_id": "portal_login:velho@x.pt", "attempts": 8,
             "last_attempt_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
             "locked_until": (datetime.now(timezone.utc) - timedelta(days=3, minutes=-10)).isoformat()},
            {"_id": "portal_login:agora@x.pt", "attempts": 8,
             "last_attempt_at": datetime.now(timezone.utc).isoformat(),
             "locked_until": (datetime.now(timezone.utc) + timedelta(minutes=9)).isoformat()},
        ])
        fake_async_db.portal_verify_attempts.docs.extend([
            {"_id": "portal_verify:a", "attempts": 2,
             "last_attempt_at": (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()},
            {"_id": "portal_verify:b", "attempts": 5,
             "last_attempt_at": datetime.now(timezone.utc).isoformat(),
             "locked_until": (datetime.now(timezone.utc) + timedelta(minutes=12)).isoformat()},
            {"_id": "portal_verify:c", "attempts": 1,
             "expire_at": datetime(2030, 1, 1, tzinfo=timezone.utc)},       # já tem
        ])
        return fake_async_db

    async def _correr(self, base, *args):
        import importlib

        sys.modules.pop("scripts.backfill_portal_attempts_ttl", None)
        modulo = importlib.import_module("scripts.backfill_portal_attempts_ttl")
        with patch("database.db", base), patch.object(sys, "argv", ["x", *args]):
            return await modulo.principal()

    @pytest.mark.asyncio
    async def test_por_omissao_le_e_nao_escreve(self, base):
        assert await self._correr(base) == 0
        por_id = {d["_id"]: d for d in base.portal_verify_attempts.docs}
        assert "expire_at" not in por_id["portal_verify:a"]
        assert "expire_at" not in por_id["portal_verify:b"]
        assert all("expire_at" not in d for d in base.portal_login_attempts.docs)

    @pytest.mark.asyncio
    async def test_aplicar_escreve_so_onde_falta_e_e_idempotente(self, base):
        await self._correr(base, "--aplicar")
        por_id = {d["_id"]: d for d in base.portal_verify_attempts.docs}

        # há 9 dias: já passou o prazo (o TTL apaga-o)
        assert por_id["portal_verify:a"]["expire_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
        # o bloqueio em curso sobrevive à purga
        assert por_id["portal_verify:b"]["expire_at"].replace(tzinfo=timezone.utc) > \
            datetime.fromisoformat(por_id["portal_verify:b"]["locked_until"])
        # o que já tinha data não é tocado
        assert por_id["portal_verify:c"]["expire_at"] == datetime(2030, 1, 1, tzinfo=timezone.utc)

        antes = [dict(d) for d in base.portal_verify_attempts.docs]
        await self._correr(base, "--aplicar")
        assert base.portal_verify_attempts.docs == antes

    @pytest.mark.asyncio
    async def test_cobre_tambem_o_login_por_email(self, base):
        await self._correr(base, "--aplicar")
        por_id = {d["_id"]: d for d in base.portal_login_attempts.docs}

        assert por_id["portal_login:velho@x.pt"]["expire_at"].replace(tzinfo=timezone.utc) < \
            datetime.now(timezone.utc)
        # o bloqueio em curso do login também sobrevive à purga
        assert por_id["portal_login:agora@x.pt"]["expire_at"].replace(tzinfo=timezone.utc) > \
            datetime.fromisoformat(por_id["portal_login:agora@x.pt"]["locked_until"])

    @pytest.mark.asyncio
    async def test_uma_corrida_com_a_aplicacao_nao_pisa_a_data_que_ela_gravou(self, base):
        """Entre a leitura e a escrita a aplicação pode gravar o seu `expire_at`
        (uma falha nova). O `update_one` é condicionado a ele ainda faltar: sem
        a condição o backfill recuava um prazo fresco para um antigo."""
        colecao = base.portal_verify_attempts
        fresco = datetime(2031, 1, 1, tzinfo=timezone.utc)

        class _Cursor:
            def __init__(self, docs):
                self._docs = docs

            async def to_list(self, _n):
                return self._docs

        # A leitura devolve um registo SEM data (como era quando o script leu)…
        desatualizado = {"_id": "portal_verify:a", "last_attempt_at": "2020-01-01T00:00:00+00:00"}
        colecao.find = lambda *_a, **_k: _Cursor([desatualizado])
        # …mas, entretanto, a aplicação já gravou o dela.
        for doc in colecao.docs:
            if doc["_id"] == "portal_verify:a":
                doc["expire_at"] = fresco

        await self._correr(base, "--aplicar")

        gravado = next(d for d in colecao.docs if d["_id"] == "portal_verify:a")
        assert gravado["expire_at"] == fresco


# ════════════════════════════════════════════════════════════════════
class TestOLoginPorEmailTemOMesmoTTL:
    AMBITO = portal_brute_force.AMBITO_DO_LOGIN
    CHAVE_LOGIN = portal_brute_force.chave_do_travao(AMBITO, "alguem@x.pt")

    @pytest.mark.asyncio
    async def test_a_falha_grava_um_datetime_nativo_que_desliza(self, fake_async_db):
        tentativas = fake_async_db.portal_login_attempts
        await tentativas.insert_one({
            "_id": self.CHAVE_LOGIN, "attempts": 1,
            "expire_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        })
        antes = datetime.now(timezone.utc)
        await portal_brute_force.registar_falha(fake_async_db, self.AMBITO, "alguem@x.pt")

        doc = await tentativas.find_one({"_id": self.CHAVE_LOGIN})
        assert isinstance(doc[_indice_do_login()["field"]], datetime)
        expira = doc["expire_at"].replace(tzinfo=timezone.utc)
        assert expira >= antes + timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_o_registo_sobrevive_ao_bloqueio_inteiro(self, fake_async_db):
        for _ in range(portal_brute_force.MAX_TENTATIVAS):
            await portal_brute_force.registar_falha(fake_async_db, self.AMBITO, "alguem@x.pt")

        doc = await fake_async_db.portal_login_attempts.find_one({"_id": self.CHAVE_LOGIN})
        bloqueado_ate = datetime.fromisoformat(doc["locked_until"])
        assert doc["expire_at"].replace(tzinfo=timezone.utc) - bloqueado_ate >= timedelta(minutes=10)

    @pytest.mark.asyncio
    async def test_antes_da_purga_o_bloqueio_vale_e_depois_o_cliente_entra(self, fake_async_db):
        """O defeito: com `attempts >= MAX` cada pedido renovava o bloqueio,
        mesmo depois de o `locked_until` ter passado — trancado para sempre.
        Só a purga do registo (o TTL) devolve o contador a zero."""
        from fastapi import HTTPException

        for _ in range(portal_brute_force.MAX_TENTATIVAS):
            await portal_brute_force.registar_falha(fake_async_db, self.AMBITO, "alguem@x.pt")
        colecao = fake_async_db.portal_login_attempts
        # o bloqueio de 10 min já passou, o registo ainda não foi purgado
        for d in colecao.docs:
            d["locked_until"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        with pytest.raises(HTTPException) as erro:
            await portal_brute_force.exigir_sem_bloqueio(fake_async_db, self.AMBITO, "alguem@x.pt")
        assert erro.value.status_code == 429          # a janela até à purga

        await colecao.delete_one({"_id": self.CHAVE_LOGIN})   # o que o TTL faz
        await portal_brute_force.exigir_sem_bloqueio(fake_async_db, self.AMBITO, "alguem@x.pt")

    def test_as_duas_portas_partilham_o_mesmo_prazo(self):
        assert portal_security.VERIFY_ATTEMPTS_TTL_MINUTES == portal_brute_force.MINUTOS_DE_VIDA_DO_REGISTO == 30
        assert portal_brute_force.MINUTOS_DE_VIDA_DO_REGISTO > portal_brute_force.MINUTOS_DE_BLOQUEIO

    def test_a_data_sai_da_mesma_funcao_nas_duas_portas(self):
        assert not hasattr(portal_security, "expira_em"), "o `verify` já não escreve datas à mão: usa o ponto único"
