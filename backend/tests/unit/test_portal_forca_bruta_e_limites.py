"""Testes unitários — D-4 no Portal: travão de tentativas + limites.

O DEFEITO (LOTE 10)
===================
O `run_verify_portal_login` — o ecrã de entrada do Portal, que pede **NIF
+ número do processo** — prometia na docstring «Protecção contra
brute-force: 5 tentativas, lockout de 15 min» e **não tinha uma linha de
código a contar tentativas**. Terceira guarda deste projecto que vive na
documentação e não no código, e a pior das três: a frase é exactamente o
que faz alguém não ir verificar.

O ataque é concreto: o `client_id` vem no link do Portal, o
`process_number` é um inteiro SEQUENCIAL e o NIF tem nove dígitos com
dígito de controlo. Fixando um e iterando o outro, o espaço de busca é
pequeno — e não havia tecto nenhum.

PORQUE É QUE O LIMITE DE PEDIDOS NÃO BASTA
==========================================
Nos endpoints de pré-autenticação não há JWT, logo a chave do
`@limiter.limit` cai no IP — e o IP sai do `X-Forwarded-For`, um
cabeçalho que o CLIENTE envia. Quem ataca varia-o e o limite não morde.
Os dois eixos são precisos: o limite é a primeira linha, o travão por
identidade é a parede.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from services.portal_brute_force import (
    AMBITO_DO_LOGIN,
    AMBITO_DO_VERIFY,
    MAX_TENTATIVAS,
    MINUTOS_DE_BLOQUEIO,
    chave_do_travao,
    esgotou_as_tentativas,
    exigir_sem_bloqueio,
    limpar,
    registar_falha,
    segundos_de_bloqueio,
)

AGORA = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)


class TestADecisaoPura:
    """O relógio entra por parâmetro — nada aqui lê a hora do sistema."""

    def test_sem_registo_nao_ha_bloqueio(self):
        assert segundos_de_bloqueio(None, agora=AGORA) == 0
        assert segundos_de_bloqueio({}, agora=AGORA) == 0

    def test_um_bloqueio_no_futuro_conta_os_segundos(self):
        doc = {"locked_until": (AGORA + timedelta(minutes=7)).isoformat()}
        assert segundos_de_bloqueio(doc, agora=AGORA) == 7 * 60

    def test_um_bloqueio_expirado_nao_bloqueia(self):
        doc = {"locked_until": (AGORA - timedelta(minutes=1)).isoformat()}
        assert segundos_de_bloqueio(doc, agora=AGORA) == 0

    @pytest.mark.parametrize("valor", ["", "   ", "ontem", None, 12345, []])
    def test_uma_data_ilegivel_NAO_bloqueia(self, valor):
        """Um registo corrompido não pode trancar um cliente legítimo
        para sempre. O travão existe para travar quem adivinha."""
        assert segundos_de_bloqueio({"locked_until": valor}, agora=AGORA) == 0

    def test_uma_data_sem_fuso_e_lida_como_UTC(self):
        """Senão a comparação levanta `TypeError` e o travão desaparece."""
        doc = {"locked_until": (AGORA + timedelta(minutes=3)).replace(tzinfo=None).isoformat()}
        assert segundos_de_bloqueio(doc, agora=AGORA) == 3 * 60

    @pytest.mark.parametrize(
        "attempts,esperado",
        [(0, False), (1, False), (MAX_TENTATIVAS - 1, False),
         (MAX_TENTATIVAS, True), (MAX_TENTATIVAS + 50, True)],
    )
    def test_o_limite_de_tentativas(self, attempts, esperado):
        assert esgotou_as_tentativas({"attempts": attempts}) is esperado

    @pytest.mark.parametrize("valor", ["muitas", None, [], {}])
    def test_um_contador_corrompido_nao_bloqueia(self, valor):
        assert esgotou_as_tentativas({"attempts": valor}) is False

    def test_a_identidade_e_normalizada(self):
        """Um travão que se contorna com a tecla de maiúsculas não é um
        travão: `A@B.PT` e `a@b.pt` são a mesma conta."""
        assert (
            chave_do_travao(AMBITO_DO_LOGIN, "  Cliente@Exemplo.PT ")
            == chave_do_travao(AMBITO_DO_LOGIN, "cliente@exemplo.pt")
        )

    def test_os_ambitos_nao_se_misturam(self):
        """Tentativas de login por email não gastam as tentativas de
        verificação por processo: são portas diferentes."""
        assert (
            chave_do_travao(AMBITO_DO_LOGIN, "x")
            != chave_do_travao(AMBITO_DO_VERIFY, "x")
        )


class _ColeccaoFalsa:
    """Só o que o travão usa. Deliberadamente simples: a lógica dos
    veredictos está nas funções PURAS acima, afirmada lá."""

    def __init__(self, docs=None, *, rebenta=False):
        self.docs = dict(docs or {})
        self.rebenta = rebenta
        self.escritas: list[dict] = []

    async def find_one(self, filtro):
        if self.rebenta:
            raise RuntimeError("base de dados em baixo")
        return self.docs.get(filtro["_id"])

    async def update_one(self, filtro, update, upsert=False):
        if self.rebenta:
            raise RuntimeError("base de dados em baixo")
        self.escritas.append({"filtro": filtro, "update": update})
        doc = self.docs.setdefault(filtro["_id"], {"_id": filtro["_id"]})
        for campo, valor in (update.get("$inc") or {}).items():
            doc[campo] = int(doc.get(campo, 0)) + valor
        doc.update(update.get("$set") or {})
        for campo, valor in (update.get("$setOnInsert") or {}).items():
            doc.setdefault(campo, valor)
        return None

    async def delete_one(self, filtro):
        if self.rebenta:
            raise RuntimeError("base de dados em baixo")
        self.docs.pop(filtro["_id"], None)


class _BDFalsa:
    def __init__(self, coleccao):
        self.portal_login_attempts = coleccao


@pytest.mark.asyncio
class TestOTravao:
    async def test_as_primeiras_tentativas_passam(self):
        bd = _BDFalsa(_ColeccaoFalsa())
        for _ in range(MAX_TENTATIVAS - 1):
            await exigir_sem_bloqueio(bd, AMBITO_DO_VERIFY, "cli-1")
            await registar_falha(bd, AMBITO_DO_VERIFY, "cli-1")
        await exigir_sem_bloqueio(bd, AMBITO_DO_VERIFY, "cli-1")

    async def test_a_tentativa_seguinte_ao_limite_e_429(self):
        coleccao = _ColeccaoFalsa()
        bd = _BDFalsa(coleccao)
        for _ in range(MAX_TENTATIVAS):
            await registar_falha(bd, AMBITO_DO_VERIFY, "cli-1")

        with pytest.raises(HTTPException) as erro:
            await exigir_sem_bloqueio(bd, AMBITO_DO_VERIFY, "cli-1")

        assert erro.value.status_code == 429
        assert erro.value.headers["Retry-After"]
        assert int(erro.value.headers["Retry-After"]) <= MINUTOS_DE_BLOQUEIO * 60

    async def test_o_bloqueio_e_carimbado_pelo_proprio_registo(self):
        coleccao = _ColeccaoFalsa()
        bd = _BDFalsa(coleccao)
        for _ in range(MAX_TENTATIVAS):
            await registar_falha(bd, AMBITO_DO_VERIFY, "cli-1")

        doc = coleccao.docs[chave_do_travao(AMBITO_DO_VERIFY, "cli-1")]
        assert doc.get("locked_until"), (
            "sem `locked_until` as tentativas ficavam no limite e o travão "
            "nunca fechava a janela"
        )

    async def test_um_cliente_de_outro_processo_nao_e_afectado(self):
        bd = _BDFalsa(_ColeccaoFalsa())
        for _ in range(MAX_TENTATIVAS + 2):
            await registar_falha(bd, AMBITO_DO_VERIFY, "cli-atacado")

        # O travão é por IDENTIDADE: o vizinho entra normalmente.
        await exigir_sem_bloqueio(bd, AMBITO_DO_VERIFY, "cli-vizinho")

    async def test_uma_entrada_bem_sucedida_LIMPA_o_contador(self):
        """Um contador que só sobe mede a vida da conta, não um ataque:
        oito erros espalhados por semanas acabavam por bloquear um
        cliente que nunca errou duas vezes seguidas."""
        coleccao = _ColeccaoFalsa()
        bd = _BDFalsa(coleccao)
        for _ in range(MAX_TENTATIVAS - 1):
            await registar_falha(bd, AMBITO_DO_VERIFY, "cli-1")

        await limpar(bd, AMBITO_DO_VERIFY, "cli-1")

        assert coleccao.docs == {}
        for _ in range(MAX_TENTATIVAS - 1):
            await exigir_sem_bloqueio(bd, AMBITO_DO_VERIFY, "cli-1")
            await registar_falha(bd, AMBITO_DO_VERIFY, "cli-1")

    async def test_a_primeira_tentativa_e_PRESERVADA(self):
        """Reescrever o `primeira_em` em cada falha fazia um ataque de
        três dias parecer começado agora — a regra do `desde` do
        `mailbox_health`."""
        coleccao = _ColeccaoFalsa()
        bd = _BDFalsa(coleccao)
        await registar_falha(bd, AMBITO_DO_VERIFY, "cli-1")
        primeira = coleccao.docs[chave_do_travao(AMBITO_DO_VERIFY, "cli-1")]["primeira_em"]
        await registar_falha(bd, AMBITO_DO_VERIFY, "cli-1")
        assert (
            coleccao.docs[chave_do_travao(AMBITO_DO_VERIFY, "cli-1")]["primeira_em"]
            == primeira
        )

    async def test_a_base_de_dados_em_baixo_NAO_tranca_o_portal(self):
        """Falhar a LER o travão deixa passar, com aviso. A alternativa
        era a base de dados com um soluço a fechar o Portal à chave a
        todos os clientes."""
        bd = _BDFalsa(_ColeccaoFalsa(rebenta=True))
        await exigir_sem_bloqueio(bd, AMBITO_DO_VERIFY, "cli-1")

    async def test_falhar_a_escrever_nao_propaga(self):
        """Mas fica no log: se não se consegue contar, o travão não
        existe, e isso não pode ser invisível."""
        bd = _BDFalsa(_ColeccaoFalsa(rebenta=True))
        await registar_falha(bd, AMBITO_DO_VERIFY, "cli-1")
        await limpar(bd, AMBITO_DO_VERIFY, "cli-1")


@pytest.mark.asyncio
class TestOVerifyUsaOTravao:
    """A LIGAÇÃO — sem ela o módulo é código morto, como o
    `_deep_link_contacts` era."""

    async def test_o_verify_recusa_ANTES_de_olhar_para_a_credencial(self, monkeypatch):
        """A ordem é a do Incidente P0: a recusa vem primeiro, senão o
        código de resposta da verificação continua a ser um oráculo sobre
        a credencial para quem já esgotou as tentativas."""
        from services import portal_auth

        coleccao = _ColeccaoFalsa()
        monkeypatch.setattr(portal_auth, "db", _BDFalsa(coleccao))

        chamadas = []

        async def nunca(**kwargs):
            chamadas.append(kwargs)
            raise HTTPException(status_code=401, detail="erradas")

        monkeypatch.setattr(portal_auth, "verify_client_credentials", nunca)

        for _ in range(MAX_TENTATIVAS):
            with pytest.raises(HTTPException):
                await portal_auth.run_verify_portal_login(
                    "cli-1", {"nif": "123456789", "process_number": 1}
                )

        feitas = len(chamadas)
        with pytest.raises(HTTPException) as erro:
            await portal_auth.run_verify_portal_login(
                "cli-1", {"nif": "123456789", "process_number": 2}
            )

        assert erro.value.status_code == 429
        assert len(chamadas) == feitas, (
            "a credencial foi verificada depois do bloqueio — o endpoint "
            "continua a responder ao ataque"
        )

    async def test_um_corpo_mal_formado_nao_gasta_tentativas(self, monkeypatch):
        """Um 400 não é uma adivinha. Contá-lo deixava um cliente com o
        formulário a dar erro a caminho do bloqueio."""
        from services import portal_auth

        coleccao = _ColeccaoFalsa()
        monkeypatch.setattr(portal_auth, "db", _BDFalsa(coleccao))

        for _ in range(MAX_TENTATIVAS + 3):
            with pytest.raises(HTTPException) as erro:
                await portal_auth.run_verify_portal_login("cli-1", {"nif": ""})
            assert erro.value.status_code == 400

        assert coleccao.docs == {}, "um corpo inválido não conta como tentativa"

    async def test_o_verify_bem_sucedido_limpa_o_contador(self, monkeypatch):
        from services import portal_auth

        coleccao = _ColeccaoFalsa()
        monkeypatch.setattr(portal_auth, "db", _BDFalsa(coleccao))

        async def falha(**kwargs):
            raise HTTPException(status_code=401, detail="erradas")

        async def acerta(**kwargs):
            return {
                "process_id": "p-1",
                "client_id": "cli-1",
                "client_name": "Ana",
                "process_number": 12,
            }

        monkeypatch.setattr(portal_auth, "verify_client_credentials", falha)
        for _ in range(MAX_TENTATIVAS - 1):
            with pytest.raises(HTTPException):
                await portal_auth.run_verify_portal_login(
                    "cli-1", {"nif": "123456789", "process_number": 1}
                )
        assert coleccao.docs

        monkeypatch.setattr(portal_auth, "verify_client_credentials", acerta)
        monkeypatch.setattr(
            portal_auth, "create_verified_session_token",
            lambda **kwargs: "token-de-teste",
        )
        await portal_auth.run_verify_portal_login(
            "cli-1", {"nif": "123456789", "process_number": 12}
        )
        assert coleccao.docs == {}


class TestOInventarioDosNoveEndpoints:
    """Guarda de inventário: falha por OMISSÃO.

    A D-4 mediu e NOMEOU nove POST do Portal sem limite. Esta guarda não
    confia na memória de ninguém: lê as rotas e exige o limite em cada
    um. Um endpoint novo no Portal que apareça sem limite fica vermelho
    aqui, que é o que a dívida pedia para fechar.
    """

    #: Os nove nomeados na D-4 (medição do Lote 9).
    OS_NOVE = {
        "portal_login",
        "verify_portal_login",
        "authenticate_portal",
        "update_client_profile",
        "send_portal_message",
        "fetch_financas_documents",
        "fetch_seguranca_social_documents",
        "submit_mfa_code",
        "create_recommendations",
    }

    @staticmethod
    def _funcoes():
        arvore = ast.parse(Path("routes/portal.py").read_text(encoding="utf-8"))
        return {
            no.name: no
            for no in ast.walk(arvore)
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_os_nove_tem_limite(self):
        funcoes = self._funcoes()
        for nome in sorted(self.OS_NOVE):
            assert nome in funcoes, f"{nome} desapareceu de routes/portal.py"
            decoradores = [ast.unparse(d) for d in funcoes[nome].decorator_list]
            assert any(d.startswith("limiter.limit(") for d in decoradores), (
                f"'{nome}' é um dos nove da D-4 e continua sem @limiter.limit"
            )

    def test_os_nove_declaram_request_E_response(self):
        """`response` não é decorativo: sem ele o caminho de SUCESSO
        devolve 500 (incidente de Set 2026, onze dos catorze)."""
        funcoes = self._funcoes()
        for nome in sorted(self.OS_NOVE):
            anotacoes = {
                arg.arg: ast.unparse(arg.annotation) if arg.annotation else ""
                for arg in funcoes[nome].args.args
            }
            assert anotacoes.get("request") == "Request", (
                f"'{nome}' tem limite e não recebe `Request`"
            )
            assert anotacoes.get("response") == "Response", (
                f"'{nome}' tem limite e não declara `response: Response` — o "
                "caminho de sucesso devolve 500"
            )

    def test_a_contraprova_o_leitor_ve_mesmo_as_rotas(self):
        """Sem isto, um extractor que devolvesse pouco passava sempre."""
        funcoes = self._funcoes()
        assert self.OS_NOVE <= set(funcoes)
        decoradores_de_escrita = [
            d
            for no in funcoes.values()
            for d in map(ast.unparse, no.decorator_list)
            if d.startswith("router.post(")
        ]
        assert len(decoradores_de_escrita) >= 9

    def test_nenhum_POST_do_portal_fica_sem_limite(self):
        """O sentido mais forte: deriva das ROTAS, não da lista.

        A lista dos nove é história; esta asserção é a propriedade. Um
        POST novo sem limite falha aqui sem ninguém se lembrar de o
        acrescentar a lista nenhuma.
        """
        funcoes = self._funcoes()
        sem_limite = []
        for nome, no in funcoes.items():
            decoradores = [ast.unparse(d) for d in no.decorator_list]
            escreve = any(
                d.startswith(("router.post(", "router.put(", "router.patch(",
                              "router.delete("))
                for d in decoradores
            )
            if not escreve:
                continue
            if not any(d.startswith("limiter.limit(") for d in decoradores):
                sem_limite.append(nome)

        assert sem_limite == [], (
            "endpoints de ESCRITA do Portal sem limite de pedidos: "
            f"{sorted(sem_limite)}"
        )

class TestOCaminhoDoSUCESSODevolve200:
    """O que uma bateria de recusas nunca prova.

    Em Set 2026, ONZE dos catorze endpoints limitados devolviam **500 no
    caminho de sucesso**: o slowapi corre com `headers_enabled=True` e
    precisa de um objecto `Response` para acrescentar os `X-RateLimit-*`,
    que procura no valor devolvido ou no parâmetro `response`. A injecção
    corre **apenas quando o handler DEVOLVE** — num caminho de erro a
    excepção sobe antes, e por isso uma bateria de rejeições fica verde
    sobre endpoints inutilizáveis.

    Este teste monta uma app REAL com o limiter REAL e exige 200 + os
    cabeçalhos. Um duplo do slowapi reimplementaria exactamente a escolha
    que falhou.
    """

    @staticmethod
    def _app(monkeypatch, nome_do_handler, resposta):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from slowapi.errors import RateLimitExceeded

        from middleware.rate_limit import limiter, rate_limit_exceeded_handler
        from routes import portal as rotas

        async def falso(*args, **kwargs):
            return resposta

        monkeypatch.setattr(rotas, nome_do_handler, falso)

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
        app.include_router(rotas.router, prefix="/api")
        return TestClient(app)

    def test_o_login_do_portal_responde_200_e_com_cabecalhos(self, monkeypatch):
        cliente = self._app(
            monkeypatch, "run_portal_login", {"token": "t", "client_id": "c"}
        )
        resposta = cliente.post(
            "/api/portal/auth/login",
            json={"email": "ana@exemplo.pt", "access_code": "A4B9X2"},
        )

        assert resposta.status_code == 200, resposta.text
        assert "x-ratelimit-limit" in {k.lower() for k in resposta.headers}

    def test_o_verify_responde_200_e_com_cabecalhos(self, monkeypatch):
        cliente = self._app(
            monkeypatch, "run_verify_portal_login", {"token": "t"}
        )
        resposta = cliente.post(
            "/api/portal/cli-1/verify",
            json={"nif": "123456789", "process_number": 12},
        )

        assert resposta.status_code == 200, resposta.text
        assert "x-ratelimit-limit" in {k.lower() for k in resposta.headers}

    def test_o_429_do_limite_tambem_e_o_do_limiter_real(self, monkeypatch):
        """E ao décimo primeiro pedido o limite MORDE.

        Prova que o decorador está ligado e não só declarado — sem isto,
        um `@limiter.limit` com um nome mal escrito passaria os dois
        testes acima.
        """
        cliente = self._app(
            monkeypatch, "run_portal_login", {"token": "t"}
        )
        corpo = {"email": "forca.bruta@exemplo.pt", "access_code": "A4B9X2"}
        codigos = [
            cliente.post(
                "/api/portal/auth/login",
                json=corpo,
                headers={"X-Forwarded-For": "203.0.113.77"},
            ).status_code
            for _ in range(12)
        ]

        assert codigos.count(200) == 10, codigos
        assert codigos[-1] == 429, codigos
