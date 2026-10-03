"""Unicidade de NIF/Email dos clientes — criação E edição (Lote 2, ponto 4).

O DEFEITO
=========
`run_create_client` recusava um NIF/email repetido com 409. O
`run_update_client` **não verificava nada**: abrir um cliente, trocar o
NIF para o de outro e gravar deixava dois clientes com o mesmo NIF, sem
erro em sítio nenhum.

A porta da frente estava fechada e a janela ao lado estava aberta — e é
a janela a mais perigosa, porque fabrica a colisão em cima de dados que
já existem.

O QUE ESTES TESTES PROVAM, E PORQUE É QUE SÃO ASSIM
===================================================
1. **A edição recusa** (o defeito).
2. **A edição deixa gravar o próprio cliente** — a contraprova. Sem ela,
   "recusa sempre" passava o teste 1 e tornava a edição impossível. É o
   erro óbvio de quem copia a condição da criação para a edição, logo
   tem de ter teste próprio.
3. **Os dois caminhos usam a MESMA função** — afirmado sobre o
   código-fonte das duas, mais a contraprova de que a função chamada é
   mesmo a que recusa. Sem a contraprova, apagar o corpo de
   `assert_cliente_unico` satisfazia a guarda.
4. **O índice cego e o valor em claro** — os dois ramos, porque só o
   hash deixaria passar duplicados sobre os dados mais antigos da base
   (os que ainda não foram migrados).
5. **Um cliente eliminado não bloqueia** — regra de negócio herdada da
   criação, que se perde sem teste.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import client_uniqueness as cu  # noqa: E402
from services.encryption import generate_email_hash, generate_nif_hash  # noqa: E402
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios  # noqa: E402

NIF_A = "123456789"
NIF_B = "987654321"
EMAIL_A = "ana@exemplo.pt"
EMAIL_B = "bruno@exemplo.pt"


def _cliente(id_: str, *, nif=None, email=None, nome="Cliente", cifrado=False, **extra) -> dict:
    """Um cliente como está em base.

    `cifrado=True` imita um registo migrado: o valor em claro saiu e
    ficou só o índice cego. É esse o estado da maior parte da base, e um
    teste que só use valores em claro não prova nada sobre ela.
    """
    dados: dict = {}
    contacto: dict = {}
    if nif:
        dados["nif_hash"] = generate_nif_hash(nif)
        if not cifrado:
            dados["nif"] = nif
    if email:
        contacto["email_hash"] = generate_email_hash(email)
        if not cifrado:
            contacto["email"] = email.lower()
    return {"id": id_, "nome": nome, "dados_pessoais": dados, "contacto": contacto, **extra}


@pytest.fixture
def db_com_a_ana(fake_async_db, monkeypatch):
    """Base com UM cliente: a Ana, com NIF_A e EMAIL_A."""
    fake_async_db.clients.docs.append(_cliente("cli-ana", nif=NIF_A, email=EMAIL_A, nome="Ana Silva"))
    monkeypatch.setattr(cu, "db", fake_async_db)
    return fake_async_db


class TestAEdicaoRecusaODuplicado:
    """O defeito: a edição não tinha guarda nenhuma."""

    @pytest.mark.asyncio
    async def test_nao_posso_passar_o_nif_da_ana_para_outro_cliente(self, db_com_a_ana):
        with pytest.raises(HTTPException) as erro:
            await cu.assert_cliente_unico(NIF_A, None, excluir_id="cli-bruno")
        assert erro.value.status_code == 409
        assert erro.value.detail["existing_client_id"] == "cli-ana"
        assert erro.value.detail["matched_fields"] == ["nif"]

    @pytest.mark.asyncio
    async def test_nao_posso_passar_o_email_da_ana_para_outro_cliente(self, db_com_a_ana):
        with pytest.raises(HTTPException) as erro:
            await cu.assert_cliente_unico(None, EMAIL_A, excluir_id="cli-bruno")
        assert erro.value.detail["matched_fields"] == ["email"]

    @pytest.mark.asyncio
    async def test_a_mensagem_diz_QUAL_o_campo_em_conflito(self, db_com_a_ana):
        """"NIF ou Email" obriga quem preenche a adivinhar qual corrigir."""
        with pytest.raises(HTTPException) as so_nif:
            await cu.assert_cliente_unico(NIF_A, EMAIL_B, excluir_id="cli-x")
        assert "NIF" in so_nif.value.detail["message"]
        assert "Email" not in so_nif.value.detail["message"]

        with pytest.raises(HTTPException) as so_email:
            await cu.assert_cliente_unico(NIF_B, EMAIL_A, excluir_id="cli-x")
        assert "Email" in so_email.value.detail["message"]

    @pytest.mark.asyncio
    async def test_o_nome_do_cliente_existente_vai_na_resposta(self, db_com_a_ana):
        """Sem o nome, a UI diz "já existe" e ninguém sabe onde ir ver."""
        with pytest.raises(HTTPException) as erro:
            await cu.assert_cliente_unico(NIF_A, None, excluir_id="cli-x")
        assert erro.value.detail["existing_client_name"] == "Ana Silva"


class TestAEdicaoDeixaGravarOProprioCliente:
    """CONTRAPROVA. Sem isto, "recusa sempre" passava os testes acima e
    tornava a edição de qualquer cliente impossível."""

    @pytest.mark.asyncio
    async def test_gravar_a_ana_com_o_nif_dela_propria_passa(self, db_com_a_ana):
        await cu.assert_cliente_unico(NIF_A, EMAIL_A, excluir_id="cli-ana")

    @pytest.mark.asyncio
    async def test_sem_excluir_id_a_ana_casava_consigo_propria(self, db_com_a_ana):
        """É isto que o `excluir_id` existe para evitar — e é o erro que se
        comete ao reutilizar a condição da criação na edição sem pensar."""
        with pytest.raises(HTTPException):
            await cu.assert_cliente_unico(NIF_A, EMAIL_A)

    @pytest.mark.asyncio
    async def test_um_nif_novo_passa(self, db_com_a_ana):
        await cu.assert_cliente_unico(NIF_B, EMAIL_B, excluir_id="cli-bruno")

    @pytest.mark.asyncio
    async def test_sem_nif_e_sem_email_nao_ha_nada_a_verificar(self, db_com_a_ana):
        """Uma edição que só mexe no telefone não pode ser recusada."""
        await cu.assert_cliente_unico(None, None, excluir_id="cli-bruno")
        await cu.assert_cliente_unico("", "   ", excluir_id="cli-bruno")


class TestOsDoisRamosDaProcura:
    """O índice cego apanha os migrados; o valor em claro apanha os antigos."""

    @pytest.mark.asyncio
    async def test_apanha_um_cliente_JA_MIGRADO_so_pelo_hash(self, fake_async_db, monkeypatch):
        fake_async_db.clients.docs.append(
            _cliente("cli-migrada", nif=NIF_A, email=EMAIL_A, cifrado=True)
        )
        monkeypatch.setattr(cu, "db", fake_async_db)
        with pytest.raises(HTTPException):
            await cu.assert_cliente_unico(NIF_A, None, excluir_id="outro")

    @pytest.mark.asyncio
    async def test_apanha_um_cliente_ANTIGO_so_pelo_valor_em_claro(self, fake_async_db, monkeypatch):
        """Registo sem índice cego: é o caso dos dados por migrar, e é
        exactamente o que uma condição só com hash deixava passar."""
        fake_async_db.clients.docs.append(
            {"id": "cli-antiga", "nome": "Antiga",
             "dados_pessoais": {"nif": NIF_A}, "contacto": {"email": EMAIL_A}}
        )
        monkeypatch.setattr(cu, "db", fake_async_db)
        with pytest.raises(HTTPException):
            await cu.assert_cliente_unico(NIF_A, None, excluir_id="outro")
        with pytest.raises(HTTPException):
            await cu.assert_cliente_unico(None, EMAIL_A, excluir_id="outro")

    def test_a_condicao_leva_MESMO_os_dois_ramos(self):
        """Contraprova de cobertura: se um dos ramos cair, os testes acima
        continuariam verdes pelo outro."""
        condicoes = cu.construir_condicoes_de_duplicado(NIF_A, EMAIL_A)
        chaves = {chave for c in condicoes for chave in c}
        assert chaves == {
            "dados_pessoais.nif_hash",
            "dados_pessoais.nif",
            "contacto.email_hash",
            "contacto.email",
        }

    def test_o_email_e_comparado_sem_depender_de_maiusculas(self):
        condicoes = cu.construir_condicoes_de_duplicado(None, "  ANA@Exemplo.PT ")
        em_claro = [c["contacto.email"] for c in condicoes if "contacto.email" in c]
        assert em_claro == [EMAIL_A]

    @pytest.mark.asyncio
    async def test_maiusculas_no_email_submetido_nao_contornam_a_guarda(self, db_com_a_ana):
        with pytest.raises(HTTPException):
            await cu.assert_cliente_unico(None, "ANA@EXEMPLO.PT", excluir_id="outro")


class TestUmClienteEliminadoNaoBloqueia:
    """Regra de negócio herdada da criação: recriar um cliente apagado por
    engano não tem de obrigar a restaurá-lo primeiro."""

    @pytest.mark.asyncio
    async def test_is_deleted_nao_bloqueia(self, fake_async_db, monkeypatch):
        fake_async_db.clients.docs.append(
            _cliente("cli-morta", nif=NIF_A, email=EMAIL_A, is_deleted=True)
        )
        monkeypatch.setattr(cu, "db", fake_async_db)
        await cu.assert_cliente_unico(NIF_A, EMAIL_A, excluir_id="novo")

    @pytest.mark.asyncio
    async def test_status_eliminado_nao_bloqueia(self, fake_async_db, monkeypatch):
        fake_async_db.clients.docs.append(
            _cliente("cli-morta2", nif=NIF_A, email=EMAIL_A, status="eliminado")
        )
        monkeypatch.setattr(cu, "db", fake_async_db)
        await cu.assert_cliente_unico(NIF_A, EMAIL_A, excluir_id="novo")

    @pytest.mark.asyncio
    async def test_mas_um_cliente_ACTIVO_continua_a_bloquear(self, db_com_a_ana):
        """Contraprova: sem ela, "nunca bloqueia" passava os dois testes
        acima."""
        with pytest.raises(HTTPException):
            await cu.assert_cliente_unico(NIF_A, EMAIL_A, excluir_id="novo")


class TestAsDuasPortasUsamOMesmoPontoUnico:
    """Guardas sobre o código-fonte — e a contraprova ao lado, porque uma
    guarda de fonte sem contraprova é satisfeita por apagar a chamada."""

    def test_a_criacao_chama_assert_cliente_unico(self):
        from services import client_crud
        fonte = codigo_da_funcao_sem_comentarios(client_crud.run_create_client)
        assert "assert_cliente_unico" in fonte

    def test_a_edicao_chama_assert_cliente_unico(self):
        from services import client_crud
        fonte = codigo_da_funcao_sem_comentarios(client_crud.run_update_client)
        assert "assert_cliente_unico" in fonte

    def test_a_edicao_passa_excluir_id(self):
        """Sem `excluir_id`, a chamada existe e a edição fica impossível —
        a guarda acima passaria e o produto estava pior do que antes."""
        from services import client_crud
        fonte = codigo_da_funcao_sem_comentarios(client_crud.run_update_client)
        assert "excluir_id=client_id" in fonte.replace(" ", "")

    def test_a_criacao_NAO_tem_o_bloco_em_linha_que_foi_substituido(self):
        """Senão ficavam duas cópias, que é o defeito original com outro nome."""
        from services import client_crud
        fonte = codigo_da_funcao_sem_comentarios(client_crud.run_create_client)
        assert "matched_fields" not in fonte
        assert "existing_query" not in fonte

    @pytest.mark.asyncio
    async def test_CONTRAPROVA_a_funcao_chamada_recusa_mesmo(self, db_com_a_ana):
        """O elo que as guardas de fonte não conseguem afirmar."""
        with pytest.raises(HTTPException):
            await cu.assert_cliente_unico(NIF_A, None, excluir_id="outro")


class TestAEdicaoNaoVerificaOValorJaEmBASE:
    """O valor em base está ENCRIPTADO. Calcular o índice cego sobre um
    criptograma dá um hash que nunca casa — a guarda passaria calada e
    pareceria funcionar."""

    def test_a_edicao_verifica_o_que_foi_SUBMETIDO(self):
        from services import client_crud
        fonte = codigo_da_funcao_sem_comentarios(client_crud.run_update_client)
        assert "nif_submetido" in fonte and "email_submetido" in fonte
        # Nunca os dicionários já fundidos com o que está em base.
        assert "assert_cliente_unico(sanitized_dados_pessoais" not in fonte
        assert "assert_cliente_unico(sanitized_contacto" not in fonte
