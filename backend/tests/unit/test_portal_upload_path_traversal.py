"""
Testes unitários — Portal do Cliente: o `file_key` do cliente NUNCA é de confiança.

INCIDENTE P0 (Set 2026) — o que este ficheiro prova
===================================================
O `POST /portal/confirm-upload` aceitava o `file_key` do CORPO do pedido e
validava-o apenas com ``s3_service.file_exists(file_key)``. Com isso, um
cliente autenticado no Portal (um titular legítimo, com o seu magic link)
conseguia, num único pedido:

  1. nomear QUALQUER chave do bucket — ``backups/dump-2026-09-01.zip``,
     ``companies/*``, a pasta de documentos do cliente de outra rede;
  2. receber de volta um URL pré-assinado para a descarregar
     (``temporary_url`` na resposta);
  3. deixar em `db.documents` um registo com esse `s3_path` ancorado ao SEU
     processo — o que fazia o `GET /portal/download-url` (esse, bem guardado)
     passar a autorizar a mesma chave para sempre.

As duas guardas que impediam exactamente isto já existiam desde o Épico 9
(`document_process_resolve.assert_path_within_document_root` e
`assert_s3_file_belongs_to_process`), mas estavam ligadas apenas aos
endpoints do CRM. O Portal — a ÚNICA superfície exposta a utilizadores
externos — ficou fora da parede. Cada camada validava; a combinação não.

Os testes de `TestAExploracao` são a demonstração do ataque: escritos para
ficarem VERMELHOS enquanto a porta estiver aberta e verdes quando fechada.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services import portal_upload_ops as puo


# Chave do backup da base de dados — vive no MESMO bucket, noutro prefixo.
CHAVE_DO_BACKUP = "backups/dump-2026-09-01.zip"
# Pasta de documentos de um cliente de OUTRA rede (Domus vs Power).
CHAVE_DE_OUTRO_CLIENTE = "Documentação Clientes/Cliente Da Domus/Index/irs.pdf"
# Logótipos das empresas.
CHAVE_DE_LOGOTIPO = "companies/power/logo.png"
# A chave legítima deste cliente.
PASTA_LEGITIMA = "Documentação Clientes/Ana Legitima"
CHAVE_LEGITIMA = f"{PASTA_LEGITIMA}/Index/recibo.pdf"

PROCESSO = {
    "id": "proc-1",
    "client_id": "cli-1",
    "client_name": "Ana Legitima",
    "s3_folder": PASTA_LEGITIMA,
    "process_number": 12,
    "company": "empresa-power",
}

CLIENTE = {
    "id": "cli-1",
    "nome": "Ana Legitima",
    "s3_folder": PASTA_LEGITIMA,
}


# Um PDF que o `libmagic` reconhece de facto — a quarentena (Set 2026)
# inspecciona os primeiros 2 KB de tudo o que é confirmado, pelo que uma
# chave legítima já não basta: os BYTES também têm de ser válidos.
PDF_VALIDO = b"%PDF-1.7\n" + b"0" * 512


class S3Falso:
    """S3 que confirma a existência de QUALQUER chave.

    É esse o ponto: no bucket real o backup EXISTE, logo o `file_exists` do
    código de produção respondia `True` e era a única validação que havia.

    O conteúdo por omissão é um PDF VÁLIDO, de propósito: a exploração do
    incidente P0 não depende de o ficheiro ser mau, depende de a chave ser de
    outra pessoa. Misturar as duas coisas faria estes testes passarem pela
    razão errada — seria a quarentena a recusar, não a guarda de posse.
    """

    def __init__(self):
        self.chaves_assinadas: list[str] = []
        self.apagados: list[str] = []
        self.conteudos: dict[str, bytes] = {}
        self.chaves_inexistentes: set[str] = set()

    def is_configured(self) -> bool:
        return True

    def _corpo(self, object_name: str) -> bytes:
        return self.conteudos.get(object_name, PDF_VALIDO)

    def file_exists(self, object_name: str) -> bool:
        return object_name not in self.chaves_inexistentes

    def head_object_metadata(self, object_name: str):
        if object_name in self.chaves_inexistentes:
            return "ausente", None
        corpo = self._corpo(object_name)
        return "ok", {"tamanho": len(corpo), "tipo": "application/pdf", "etag": "abc"}

    def get_object_prefix(self, object_name: str, num_bytes: int):
        if object_name in self.chaves_inexistentes:
            return None
        return self._corpo(object_name)[:num_bytes]

    def delete_file(self, object_name: str) -> bool:
        self.apagados.append(object_name)
        return True

    def get_presigned_url(self, object_name: str, expiration: int = 3600):
        self.chaves_assinadas.append(object_name)
        return f"https://bucket.s3.amazonaws.com/{object_name}?X-Amz-Signature=abc"


@pytest.fixture
def s3_falso():
    return S3Falso()


@pytest.fixture
def portal(fake_async_db, s3_falso):
    """Serviço de upload do Portal com o S3, a BD e os efeitos laterais falseados.

    Só as fronteiras são falseadas — a lógica de `run_confirm_portal_upload`
    é a REAL, que é o que faz deste teste uma prova e não uma encenação.
    """
    # REGRA DO PROJECTO (AGENTS.md): cada módulo da cadeia que faça
    # `from database import db` no TOPO tem a SUA referência ao proxy — e um
    # `patch` no serviço de entrada não o apanha. Sem o
    # `document_portal_counts` aqui, o ramo do `document_id` escrevia no
    # proxy REAL e o teste rebentava com "Event loop is closed": verde ou
    # vermelho conforme a ORDEM de recolha do pytest.
    from services import document_portal_counts
    from services import s3_content_quarantine

    with patch.object(puo, "db", fake_async_db), \
         patch.object(document_portal_counts, "db", fake_async_db), \
         patch("database.db", fake_async_db), \
         patch.object(puo, "s3_service", s3_falso), \
         patch.object(s3_content_quarantine, "s3_service", s3_falso), \
         patch.object(puo, "invalidate_stats_cache", _nada_async), \
         patch("services.background_tasks.spawn_background_task", _nada_sync), \
         patch("services.history.log_history", _nada_async), \
         patch.object(puo, "send_notification_with_preference_check", _nada_async):
        yield puo


async def _nada_async(*args, **kwargs):
    return None


def _nada_sync(*args, **kwargs):
    # As corotinas passadas ao `spawn_background_task` têm de ser fechadas,
    # senão o pytest avisa "coroutine was never awaited" e o ruído esconde
    # falhas a sério.
    for arg in args:
        if hasattr(arg, "close"):
            arg.close()
    return None


def _dados_do_cliente(*, com_processo: bool = True) -> dict:
    """O `client_data` que o `get_current_client` devolve a um titular legítimo."""
    if com_processo:
        return {
            "process_id": PROCESSO["id"],
            "process": dict(PROCESSO),
            "client": dict(CLIENTE),
            "client_id": CLIENTE["id"],
            "token_payload": {"sub": PROCESSO["id"], "type": "magic_link"},
        }
    return {
        "process_id": None,
        "process": None,
        "client": dict(CLIENTE),
        "client_id": CLIENTE["id"],
        "token_payload": {"sub": CLIENTE["id"], "type": "access_code_session"},
    }


# ====================================================================
# A EXPLORAÇÃO — o teste que morde
# ====================================================================

class TestAExploracao:
    """Um cliente do Portal a pedir chaves que não são dele.

    Cada teste aqui é o ataque escrito na linguagem do código de produção.
    Enquanto a porta estiver aberta, ficam VERMELHOS.
    """

    @pytest.mark.asyncio
    async def test_o_backup_da_base_de_dados_e_recusado(self, portal, s3_falso):
        """`backups/dump-2026-09-01.zip` — a chave do incidente P0."""
        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_DO_BACKUP,
                    "original_filename": "dump-2026-09-01.zip",
                    "file_size": 10,
                    "content_type": "application/zip",
                },
                _dados_do_cliente(),
            )

        assert erro.value.status_code == 403
        # E — o que mais importa — nenhum URL foi assinado para o backup.
        assert CHAVE_DO_BACKUP not in s3_falso.chaves_assinadas

    @pytest.mark.asyncio
    async def test_nenhum_registo_fica_na_base_de_dados(self, portal, fake_async_db):
        """A recusa é ANTES da escrita.

        Se o registo nascesse, o `GET /portal/download-url` — que autoriza
        pela existência do registo — passaria a servir a chave para sempre.
        Uma recusa que deixe rasto não é uma recusa.
        """
        with pytest.raises(HTTPException):
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_DO_BACKUP,
                    "original_filename": "dump.zip",
                    "file_size": 10,
                    "content_type": "application/zip",
                },
                _dados_do_cliente(),
            )

        assert await fake_async_db.documents.find_one({"s3_path": CHAVE_DO_BACKUP}) is None
        assert await fake_async_db.documents.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_a_pasta_de_um_cliente_de_outra_rede_e_recusada(self, portal):
        """Dentro da raiz de documentos, mas de outra pessoa — e de outra REDE.

        Este é o caso que a guarda da raiz sozinha NÃO apanha: a chave começa
        por `Documentação Clientes/`. É por isso que são duas guardas.
        """
        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_DE_OUTRO_CLIENTE,
                    "original_filename": "irs.pdf",
                    "file_size": 10,
                    "content_type": "application/pdf",
                },
                _dados_do_cliente(),
            )
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_o_logotipo_da_empresa_e_recusado(self, portal):
        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_DE_LOGOTIPO,
                    "original_filename": "logo.png",
                    "file_size": 10,
                    "content_type": "image/png",
                },
                _dados_do_cliente(),
            )
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_o_fluxo_sem_processo_tambem_esta_fechado(self, portal):
        """Onboarding: o cliente ainda não tem processo, e a porta era a mesma.

        O upload sem processo ancora ao `client_id` — se a guarda só olhasse
        para o processo, este caminho ficava aberto por omissão.
        """
        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_DO_BACKUP,
                    "original_filename": "dump.zip",
                    "file_size": 10,
                    "content_type": "application/zip",
                },
                _dados_do_cliente(com_processo=False),
            )
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_satisfazer_um_pedido_do_checklist_nao_e_porta_de_serviço(
        self, portal, fake_async_db
    ):
        """Com `document_id`, o caminho do código é OUTRO (`$push` no pedido).

        Uma guarda colocada só no ramo do documento novo deixaria este
        aberto — e é o ramo que o Portal usa mais, porque a checklist é o
        caminho normal do cliente.
        """
        await fake_async_db.documents.insert_one({
            "id": "pedido-1",
            "process_id": PROCESSO["id"],
            "client_id": CLIENTE["id"],
            "status": "REQUESTED",
            "category": "IRS",
            "expected_count": 1,
        })

        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_DO_BACKUP,
                    "original_filename": "dump.zip",
                    "document_id": "pedido-1",
                    "file_size": 10,
                    "content_type": "application/zip",
                },
                _dados_do_cliente(),
            )
        assert erro.value.status_code == 403

        pedido = await fake_async_db.documents.find_one({"id": "pedido-1"})
        assert pedido["status"] == "REQUESTED", "o pedido não pode ficar satisfeito"
        assert pedido.get("s3_path") is None


# ====================================================================
# O CAMINHO LEGÍTIMO — a contraprova
# ====================================================================

class TestOUploadLegitimoContinuaAFuncionar:
    """Sem isto, fechar a porta com cimento passaria nos testes de ataque.

    É a metade que impede a "correcção" que recusa tudo.
    """

    @pytest.mark.asyncio
    async def test_o_cliente_grava_na_sua_propria_pasta(self, portal, fake_async_db):
        resposta = await portal.run_confirm_portal_upload(
            {
                "file_key": CHAVE_LEGITIMA,
                "original_filename": "recibo.pdf",
                "file_size": 1024,
                "content_type": "application/pdf",
            },
            _dados_do_cliente(),
        )

        assert resposta["success"] is True
        assert resposta["s3_path"] == CHAVE_LEGITIMA
        gravado = await fake_async_db.documents.find_one({"s3_path": CHAVE_LEGITIMA})
        assert gravado is not None
        assert gravado["process_id"] == PROCESSO["id"]
        assert gravado["client_id"] == CLIENTE["id"]

    @pytest.mark.asyncio
    async def test_o_pedido_do_checklist_continua_a_ser_satisfeito(
        self, portal, fake_async_db
    ):
        await fake_async_db.documents.insert_one({
            "id": "pedido-1",
            "process_id": PROCESSO["id"],
            "client_id": CLIENTE["id"],
            "status": "REQUESTED",
            "category": "IRS",
            "expected_count": 1,
        })

        resposta = await portal.run_confirm_portal_upload(
            {
                "file_key": CHAVE_LEGITIMA,
                "original_filename": "recibo.pdf",
                "document_id": "pedido-1",
                "file_size": 1024,
                "content_type": "application/pdf",
            },
            _dados_do_cliente(),
        )

        assert resposta["success"] is True
        pedido = await fake_async_db.documents.find_one({"id": "pedido-1"})
        assert pedido["s3_path"] == CHAVE_LEGITIMA

    @pytest.mark.asyncio
    async def test_o_onboarding_sem_processo_grava_na_pasta_do_cliente(
        self, portal, fake_async_db
    ):
        """Sem processo, o dono do prefixo é o CLIENTE."""
        resposta = await portal.run_confirm_portal_upload(
            {
                "file_key": CHAVE_LEGITIMA,
                "original_filename": "recibo.pdf",
                "file_size": 1024,
                "content_type": "application/pdf",
            },
            _dados_do_cliente(com_processo=False),
        )

        assert resposta["success"] is True
        gravado = await fake_async_db.documents.find_one({"s3_path": CHAVE_LEGITIMA})
        assert gravado is not None
        assert gravado["client_id"] == CLIENTE["id"]


# ====================================================================
# O RESÍDUO HISTÓRICO — fechar a escrita não fecha o que já foi escrito
# ====================================================================

class TestOResiduoDaJanelaVulneravel:
    """O `/portal/download-url` autoriza pela EXISTÊNCIA do registo.

    Qualquer exploração ocorrida antes deste hotfix deixou em `db.documents`
    um registo com `s3_path` estranho já ancorado ao processo do atacante —
    e esse endpoint servi-lo-ia indefinidamente. Por isso a guarda está
    também no caminho da LEITURA: os registos herdados deixam de ser
    servidos sem ser preciso limpar a colecção primeiro.
    """

    @pytest.mark.asyncio
    async def test_um_registo_envenenado_nao_e_servido(self, portal, fake_async_db):
        # Exactamente o registo que o ataque deixava para trás.
        await fake_async_db.documents.insert_one({
            "id": "doc-envenenado",
            "process_id": PROCESSO["id"],
            "s3_path": CHAVE_DO_BACKUP,
            "status": "RECEIVED",
            "uploaded_by": "portal_client",
        })

        with pytest.raises(HTTPException) as erro:
            await portal.run_get_portal_download_url(
                CHAVE_DO_BACKUP, _dados_do_cliente()
            )

        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_um_registo_envenenado_da_pasta_de_outro_cliente_nao_e_servido(
        self, portal, fake_async_db
    ):
        await fake_async_db.documents.insert_one({
            "id": "doc-envenenado-2",
            "process_id": PROCESSO["id"],
            "s3_path": CHAVE_DE_OUTRO_CLIENTE,
            "status": "RECEIVED",
        })

        with pytest.raises(HTTPException) as erro:
            await portal.run_get_portal_download_url(
                CHAVE_DE_OUTRO_CLIENTE, _dados_do_cliente()
            )
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_o_download_legitimo_continua_a_funcionar(
        self, portal, fake_async_db
    ):
        """Contraprova: sem isto, um 403 cego passaria os dois testes acima."""
        await fake_async_db.documents.insert_one({
            "id": "doc-legitimo",
            "process_id": PROCESSO["id"],
            "s3_path": CHAVE_LEGITIMA,
            "status": "RECEIVED",
        })

        resposta = await portal.run_get_portal_download_url(
            CHAVE_LEGITIMA, _dados_do_cliente()
        )
        assert resposta["success"] is True
        assert "X-Amz-Signature" in resposta["url"]


# ====================================================================
# A CARGA ÚTIL — o URL pré-assinado saiu da resposta
# ====================================================================

class TestSemUrlPreAssinadoNaResposta:
    """O `confirm-upload` devolvia um URL de LEITURA para a chave nomeada.

    Era essa a carga útil: a fuga e o pedido eram o mesmo. O cliente acabou
    de enviar o ficheiro — já o tem —, e o `ClientPortal.jsx` lê apenas
    `success`/`detail`. Retirá-lo é a diferença entre "uma guarda falha =
    fuga" e "uma guarda falha = é preciso furar o download-url também".
    """

    @pytest.mark.asyncio
    async def test_a_resposta_nao_traz_temporary_url(self, portal):
        resposta = await portal.run_confirm_portal_upload(
            {
                "file_key": CHAVE_LEGITIMA,
                "original_filename": "recibo.pdf",
                "file_size": 1024,
                "content_type": "application/pdf",
            },
            _dados_do_cliente(),
        )
        assert "temporary_url" not in resposta

    @pytest.mark.asyncio
    async def test_nenhum_url_e_assinado_no_upload(self, portal, s3_falso):
        """Mais forte do que a ausência da chave: nada é assinado."""
        await portal.run_confirm_portal_upload(
            {
                "file_key": CHAVE_LEGITIMA,
                "original_filename": "recibo.pdf",
                "file_size": 1024,
                "content_type": "application/pdf",
            },
            _dados_do_cliente(),
        )
        assert s3_falso.chaves_assinadas == []


# ====================================================================
# A GUARDA, ISOLADA
# ====================================================================

class TestDonoDoPrefixo:
    """`_dono_do_prefixo_s3` — de quem sai o prefixo autorizado."""

    def test_o_processo_vence_o_cliente(self):
        """A pasta do processo é a que o `upload-url` usa quando há processo.

        Se as duas divergirem e a guarda escolhesse a do cliente, o upload
        legítimo era recusado — e a "correcção" óbvia seria alargar ambas.
        """
        dono = puo._dono_do_prefixo_s3(
            {"s3_folder": "Documentação Clientes/Do Processo"},
            {"s3_folder": "Documentação Clientes/Do Cliente"},
        )
        assert dono["s3_folder"] == "Documentação Clientes/Do Processo"

    def test_sem_processo_o_dono_e_o_cliente(self):
        dono = puo._dono_do_prefixo_s3(None, {"s3_folder": PASTA_LEGITIMA})
        assert dono["s3_folder"] == PASTA_LEGITIMA

    def test_o_nome_do_cliente_vive_em_nome_nao_em_client_name(self):
        """A guarda partilhada fala `client_name`; o cliente grava `nome`.

        Sem a tradução, um cliente sem `s3_folder` ficava sem dono e todos
        os uploads de onboarding passavam a 403.
        """
        dono = puo._dono_do_prefixo_s3(None, {"nome": "Ana Legitima"})
        assert dono["client_name"] == "Ana Legitima"

    def test_processo_sem_marcas_cai_para_o_cliente(self):
        dono = puo._dono_do_prefixo_s3(
            {"id": "proc-1"}, {"s3_folder": PASTA_LEGITIMA}
        )
        assert dono["s3_folder"] == PASTA_LEGITIMA

    def test_sem_nada_nao_ha_dono(self):
        """E sem dono o chamador recusa — falha FECHADA.

        `assert_s3_file_belongs_to_process` com `client_name` vazio aceita
        toda a raiz `Documentação Clientes/`: no CRM é um incómodo, no Portal
        era a fuga a entrar pela porta que a devia fechar.
        """
        assert puo._dono_do_prefixo_s3(None, None) is None
        assert puo._dono_do_prefixo_s3({}, {}) is None
        assert puo._dono_do_prefixo_s3({"client_name": "   "}, {"nome": ""}) is None

    def test_sem_dono_a_guarda_recusa(self):
        with pytest.raises(HTTPException) as erro:
            puo.assert_portal_file_key_e_do_cliente(
                CHAVE_LEGITIMA, process={}, client={}
            )
        assert erro.value.status_code == 403


class TestAsDuasGuardasSaoAmbasNecessarias:
    """Nenhuma das duas sozinha fecha a porta — e é fácil pensar que sim."""

    def test_a_guarda_da_raiz_sozinha_deixa_passar_o_vizinho(self):
        """`Documentação Clientes/Outro/...` passa a guarda da raiz."""
        from services.document_process_resolve import assert_path_within_document_root

        # Não levanta: a chave ESTÁ dentro da raiz de documentos.
        assert_path_within_document_root(CHAVE_DE_OUTRO_CLIENTE)

        # É a segunda guarda que a apanha.
        with pytest.raises(HTTPException):
            puo.assert_portal_file_key_e_do_cliente(
                CHAVE_DE_OUTRO_CLIENTE, process=dict(PROCESSO), client=dict(CLIENTE)
            )

    def test_a_guarda_de_posse_sozinha_deixaria_passar_o_backup_sem_pasta(self):
        """Com um dono sem `s3_folder`, o prefixo válido é derivado do NOME.

        `backups/...` não começa por nenhum desses prefixos, logo a segunda
        guarda também o apanha aqui — mas depende do nome estar preenchido,
        e é por isso que a guarda da raiz vem primeiro e não é opcional.
        """
        with pytest.raises(HTTPException):
            puo.assert_portal_file_key_e_do_cliente(
                CHAVE_DO_BACKUP,
                process={"client_name": "Ana Legitima"},
                client=None,
            )


# ====================================================================
# OS LIMITES DE PEDIDOS — guarda sobre o código, porque não há outro modo
# ====================================================================

class TestOsEndpointsDoPortalTemLimiteDePedidos:
    """Os três endpoints não tinham limite NENHUM.

    A exploração era repetível à vontade — o varrimento do bucket chave a
    chave custava só tempo. O `/public/client-registration`, ao lado, tem
    `5/hour` desde sempre.

    Esta é uma guarda sobre o CÓDIGO e não sobre o comportamento porque o
    `slowapi` só decide com uma aplicação viva e um `Request` real: num
    teste unitário o decorador é indistinguível da sua ausência. É uma
    guarda por AST (a lista de decoradores da função), nunca uma procura de
    texto — pela terceira vez neste projecto, um `assert "limiter" in fonte`
    seria satisfeito pela linha do `import`.
    """

    ENDPOINTS_COM_LIMITE = {
        "generate_portal_upload_url",
        "confirm_portal_upload",
        "get_portal_download_url",
    }

    @staticmethod
    def _decoradores_por_funcao() -> dict[str, list[str]]:
        import ast
        from pathlib import Path

        fonte = Path("routes/portal.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        encontrados: dict[str, list[str]] = {}
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            encontrados[no.name] = [ast.unparse(d) for d in no.decorator_list]
        return encontrados

    def test_cada_endpoint_de_upload_tem_limiter_limit(self):
        decoradores = self._decoradores_por_funcao()
        for nome in sorted(self.ENDPOINTS_COM_LIMITE):
            assert nome in decoradores, f"endpoint {nome} desapareceu de routes/portal.py"
            tem_limite = any(
                d.startswith("limiter.limit(") for d in decoradores[nome]
            )
            assert tem_limite, (
                f"O endpoint '{nome}' do Portal ficou sem @limiter.limit — "
                "sem limite, a exploração do INCIDENTE P0 volta a ser repetível "
                "à vontade."
            )

    def test_cada_endpoint_de_upload_recebe_o_request(self):
        """O `slowapi` exige um parâmetro `Request` para ler a chave do limite.

        Sem ele o decorador levanta em tempo de execução — e um decorador que
        rebenta no primeiro pedido é pior do que não ter limite: o endpoint
        deixa de funcionar e alguém apaga o decorador para o repor.
        """
        import ast
        from pathlib import Path

        arvore = ast.parse(Path("routes/portal.py").read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if no.name not in self.ENDPOINTS_COM_LIMITE:
                continue
            anotacoes = [
                ast.unparse(a.annotation) if a.annotation else ""
                for a in no.args.args
            ]
            assert "Request" in anotacoes, (
                f"'{no.name}' tem @limiter.limit mas não recebe `Request`"
            )

    def test_a_contraprova_o_guarda_ve_mesmo_a_ausencia(self):
        """Sem isto, um erro no extractor faria o guarda passar sempre.

        `portal_login` não tem (nem precisa de) `@limiter.limit` — se o
        extractor lhe atribuísse um, estaria a inventar decoradores e os dois
        testes acima seriam decorativos.
        """
        decoradores = self._decoradores_por_funcao()
        assert "portal_login" in decoradores
        assert not any(
            d.startswith("limiter.limit(") for d in decoradores["portal_login"]
        )


# ====================================================================
# DUAS LACUNAS APANHADAS POR MUTAÇÃO (e não pela minha primeira leitura)
# ====================================================================

class TestAGuardaDaRaizNaoERedundante:
    """Apagar `assert_path_within_document_root` não matava nenhum teste.

    Ao princípio pareceu mutante equivalente: `assert_s3_file_belongs_to_process`
    deriva sempre prefixos que COMEÇAM por `Documentação Clientes/`, logo a
    posse implica a raiz e a guarda da raiz parecia peso morto.

    Não é. A guarda da raiz é a defesa contra um prefixo de dono ENVENENADO:
    se o `s3_folder` gravado no processo apontar para fora da árvore de
    documentos, a guarda de posse autoriza alegremente tudo o que estiver lá
    — porque, do seu ponto de vista, é a pasta do cliente. O cliente não
    consegue escrever `s3_folder` (é campo protegido no PUT /portal/me), mas
    a equipa e o `ensure_client_folder_mapping` conseguem, e um valor mau
    grava-se uma vez e vale para sempre.

    Era um TESTE FRACO meu, não um mutante equivalente — a distinção que
    este projecto já pagou para aprender três vezes.
    """

    @pytest.mark.asyncio
    async def test_um_s3_folder_que_aponta_para_os_backups_nao_autoriza_nada(
        self, portal
    ):
        processo_envenenado = dict(PROCESSO, s3_folder="backups")
        dados = _dados_do_cliente()
        dados["process"] = processo_envenenado

        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": "backups/dump-2026-09-01.zip",
                    "original_filename": "dump.zip",
                    "file_size": 1,
                    "content_type": "application/zip",
                },
                dados,
            )
        assert erro.value.status_code == 403

    def test_a_raiz_recusa_mesmo_quando_a_posse_aceitaria(self):
        """A prova directa: a posse diz sim, a raiz diz não, e ganha o não."""
        from services.document_process_resolve import (
            assert_s3_file_belongs_to_process,
        )

        dono_envenenado = {"s3_folder": "companies"}
        # A guarda de posse, sozinha, ACEITA — é o seu trabalho e ela fá-lo bem.
        assert_s3_file_belongs_to_process("companies/power/logo.png", dono_envenenado)

        # A guarda completa recusa, porque a raiz vem primeiro.
        with pytest.raises(HTTPException) as erro:
            puo.assert_portal_file_key_e_do_cliente(
                "companies/power/logo.png", process=dono_envenenado, client=None
            )
        assert erro.value.status_code == 403


class TestAOrdemDaGuardaNaoEDetalhe:
    """A guarda ANTES do `file_exists`, e há uma razão de segurança.

    Se corresse depois, o código de resposta passava a depender do CONTEÚDO
    do bucket: 403 para uma chave estranha que existe, 400 ("ficheiro não
    encontrado") para uma que não existe. Isso é um oráculo — o atacante
    perde a leitura mas mantém a capacidade de MAPEAR o bucket, adivinhando
    nomes de backups e lendo a diferença nos códigos.

    Mover a chamada para depois do `file_exists` não matava nenhum teste meu.
    Mata este.
    """

    @pytest.mark.asyncio
    async def test_chave_estranha_inexistente_da_403_e_nao_404(
        self, portal, s3_falso
    ):
        # O S3 passa a dizer que NADA existe. Hoje a inexistência chega
        # pelo `HEAD` da quarentena, que substituiu o `file_exists`
        # bloqueante — a propriedade em teste é a mesma: a guarda de posse
        # responde ANTES de o S3 ser consultado.
        s3_falso.chaves_inexistentes.update({CHAVE_DO_BACKUP, CHAVE_LEGITIMA})

        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_DO_BACKUP,
                    "original_filename": "dump.zip",
                    "file_size": 1,
                    "content_type": "application/zip",
                },
                _dados_do_cliente(),
            )

        assert erro.value.status_code == 403, (
            "A resposta a uma chave fora do âmbito não pode depender de ela "
            "existir ou não no bucket — seria um oráculo de mapeamento."
        )

    @pytest.mark.asyncio
    async def test_chave_legitima_inexistente_da_400(self, portal, s3_falso):
        """Contraprova: para a SUA pasta, o cliente ouve a verdade útil.

        Sem esta metade, um 403 indiscriminado passaria o teste acima e o
        cliente deixaria de saber que o upload para o S3 falhou.
        """
        s3_falso.chaves_inexistentes.add(CHAVE_LEGITIMA)

        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_LEGITIMA,
                    "original_filename": "recibo.pdf",
                    "file_size": 1,
                    "content_type": "application/pdf",
                },
                _dados_do_cliente(),
            )
        assert erro.value.status_code == 400


# ====================================================================
# A QUARENTENA, PONTA A PONTA PELO `confirm-upload`
# ====================================================================
# A decisão da quarentena tem a sua própria bateria
# (`test_s3_content_quarantine.py`); estes testes provam a LIGAÇÃO — que ela
# corre no sítio certo do fluxo do Portal, e que o registo na base de dados
# depende dela. Vivem aqui porque é aqui que estão as fixtures do
# `confirm-upload` do Portal, e duplicá-las era garantir que divergiriam.

ELF_DISFARCADO = (
    b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8
    + b"\x02\x00>\x00\x01\x00\x00\x00\x00\x10@\x00\x00\x00\x00\x00"
    + b"@\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 24
    + b"@\x008\x00\x01\x00@\x00\x00\x00\x00\x00" + b"\x00" * 128
)


class TestAQuarentenaNoFluxoDoPortal:
    """Um executável renomeado para `.pdf`, enviado para a pasta CERTA.

    É o caso que a guarda de posse não apanha e não tem de apanhar: a chave
    é legítima, o cliente é legítimo, o que está mau são os BYTES. Sem a
    quarentena, isto era gravado como "PDF" e ficava a ser servido por URL
    pré-assinado a quem abrisse o processo no CRM.
    """

    @pytest.mark.asyncio
    async def test_um_executavel_na_pasta_certa_e_recusado_com_400(
        self, portal, s3_falso
    ):
        s3_falso.conteudos[CHAVE_LEGITIMA] = ELF_DISFARCADO

        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_LEGITIMA,
                    "original_filename": "IRS_2025.pdf",
                    "file_size": 1024,
                    "content_type": "application/pdf",
                },
                _dados_do_cliente(),
            )

        assert erro.value.status_code == 400

    @pytest.mark.asyncio
    async def test_o_objecto_e_apagado_do_s3(self, portal, s3_falso):
        s3_falso.conteudos[CHAVE_LEGITIMA] = ELF_DISFARCADO

        with pytest.raises(HTTPException):
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_LEGITIMA,
                    "original_filename": "IRS_2025.pdf",
                    "file_size": 1024,
                },
                _dados_do_cliente(),
            )

        assert s3_falso.apagados == [CHAVE_LEGITIMA]

    @pytest.mark.asyncio
    async def test_nao_nasce_registo_na_base_de_dados(
        self, portal, s3_falso, fake_async_db
    ):
        """A ordem importa: inspeccionar ANTES de gravar.

        Um registo criado e depois desfeito deixaria uma janela em que o
        `/portal/download-url` autorizava a chave — e o ficheiro já não
        estaria lá para servir, ou pior, ainda estaria.
        """
        s3_falso.conteudos[CHAVE_LEGITIMA] = ELF_DISFARCADO

        with pytest.raises(HTTPException):
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_LEGITIMA,
                    "original_filename": "IRS_2025.pdf",
                    "file_size": 1024,
                },
                _dados_do_cliente(),
            )

        assert await fake_async_db.documents.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_um_pedido_do_checklist_nao_fica_satisfeito(
        self, portal, s3_falso, fake_async_db
    ):
        """O ramo do `document_id` — o caminho normal do cliente.

        Sem a quarentena antes dos DOIS ramos, um executável satisfazia o
        pedido de IRS e o processo avançava com base nele.
        """
        await fake_async_db.documents.insert_one({
            "id": "pedido-1",
            "process_id": PROCESSO["id"],
            "client_id": CLIENTE["id"],
            "status": "REQUESTED",
            "category": "IRS",
            "expected_count": 1,
        })
        s3_falso.conteudos[CHAVE_LEGITIMA] = ELF_DISFARCADO

        with pytest.raises(HTTPException):
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_LEGITIMA,
                    "original_filename": "IRS_2025.pdf",
                    "document_id": "pedido-1",
                    "file_size": 1024,
                },
                _dados_do_cliente(),
            )

        pedido = await fake_async_db.documents.find_one({"id": "pedido-1"})
        assert pedido["status"] == "REQUESTED"
        assert pedido.get("s3_path") is None

    @pytest.mark.asyncio
    async def test_o_tamanho_gravado_e_o_REAL_nao_o_declarado(
        self, portal, fake_async_db
    ):
        """O cliente declarou 1 byte; o objecto tem 512+.

        Era isto que fazia a base de dados acreditar que um ficheiro de 5 GB
        era um "PDF de 12 KB" — e o `file_size` alimenta quotas e relatórios.
        """
        resposta = await portal.run_confirm_portal_upload(
            {
                "file_key": CHAVE_LEGITIMA,
                "original_filename": "recibo.pdf",
                "file_size": 1,
                "content_type": "application/x-mentira",
            },
            _dados_do_cliente(),
        )

        assert resposta["success"] is True
        gravado = await fake_async_db.documents.find_one({"s3_path": CHAVE_LEGITIMA})
        assert gravado["file_size"] == len(PDF_VALIDO)
        assert gravado["content_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_uma_falha_de_leitura_da_503_e_NAO_apaga(
        self, portal, s3_falso, fake_async_db
    ):
        """Um soluço do S3 não destrói o upload legítimo de um cliente.

        O 503 diz "tenta outra vez"; o objecto fica no bucket e a
        reconfirmação resolve. Um 400 com apagar, aqui, perdia o ficheiro.
        """
        s3_falso.get_object_prefix = lambda object_name, num_bytes: None

        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_LEGITIMA,
                    "original_filename": "recibo.pdf",
                    "file_size": 1024,
                },
                _dados_do_cliente(),
            )

        assert erro.value.status_code == 503
        assert s3_falso.apagados == []
        assert await fake_async_db.documents.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_a_guarda_de_posse_corre_ANTES_da_quarentena(
        self, portal, s3_falso
    ):
        """Uma chave de outra pessoa nunca chega a ser lida.

        Se a ordem se invertesse, o backend passava a descarregar 2 KB de
        qualquer chave do bucket que um cliente nomeasse — um oráculo de
        conteúdo construído com a própria parede de segurança.
        """
        s3_falso.conteudos[CHAVE_DO_BACKUP] = PDF_VALIDO

        with pytest.raises(HTTPException) as erro:
            await portal.run_confirm_portal_upload(
                {
                    "file_key": CHAVE_DO_BACKUP,
                    "original_filename": "dump.zip",
                    "file_size": 1024,
                },
                _dados_do_cliente(),
            )

        assert erro.value.status_code == 403
        assert s3_falso.apagados == [], "nem apagar uma chave que não é dele"
