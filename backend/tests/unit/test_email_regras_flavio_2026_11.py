"""Regras do email definidas com o Flavio (2026-11-04), uma classe por resposta.

Documento de revisão: «Email e Webmail — mapa, problemas e perguntas». Respostas:
1a 2a 3a 4a (assunto e dados do cliente no «+ Novo»), 5a (modelos por empresa), 6/14 (sai da
conta do utilizador; a Caixa Geral só para Master/Admin/CEO/Diretor e Administrativo), 7a (apagar
só na própria caixa), 11a (etiqueta curta), 12a (Index só consulta).
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import services.email_compose_prefill as prefill
import services.email_process_crud as crud
import services.email_templates_drafts as modelos
from services.email_process_link import (
    assunto_tem_a_etiqueta,
    etiqueta_curta_do_processo,
    etiqueta_numerica,
    extrair_id_da_etiqueta,
    processo_da_etiqueta,
)

PROCESSO = {
    "id": "p-1",
    "process_number": 1234,
    "client_name": "Ana Silva",
    "client_email": "ana@exemplo.pt",
    "personal_data": {"nif": "123456789", "telefone": "912345678", "email": "ana@exemplo.pt"},
}


def _user(role, uid="u-1"):
    return {"id": uid, "role": role, "effective_role": role, "email": f"{uid}@x.pt", "name": uid}


# ── 1a: assunto ───────────────────────────────────────────────────────────────
class TestAssunto:
    def test_assunto_e_processo_numero_e_nome(self):
        assert prefill.montar_rascunho(PROCESSO)["subject"] == "Processo #1234 — Ana Silva"

    def test_o_assunto_nao_leva_a_etiqueta(self):
        # a etiqueta é acrescentada no envio; aqui apareceria duas vezes
        assert "[Ref:" not in prefill.montar_rascunho(PROCESSO)["subject"]

    def test_sem_numero_fica_so_o_nome(self):
        assert prefill.assunto_do_processo({"client_name": "Ana"}) == "Ana"


# ── 2a / 3a / 4a: dados do cliente na mensagem ────────────────────────────────
class TestDadosDoCliente:
    def test_o_bloco_esta_no_topo_com_os_cinco_dados(self):
        corpo = prefill.montar_rascunho(PROCESSO)["body"]
        assert corpo.startswith("Dados do cliente:")
        for esperado in ("N.º do processo: 1234", "Nome: Ana Silva", "NIF: 123456789",
                         "Telemóvel: 912345678", "Email: ana@exemplo.pt"):
            assert esperado in corpo

    def test_espaco_para_escrever_depois_do_bloco(self):
        assert prefill.montar_rascunho(PROCESSO)["body"].endswith("\n\n\n")

    def test_segundo_titular_entra_quando_existe(self):
        p = {**PROCESSO, "titular2_data": {"name": "Rui Silva", "nif": "987654321", "email": "rui@x.pt"}}
        corpo = prefill.bloco_dados_do_cliente(p)
        assert "2.º titular:" in corpo and "Nome: Rui Silva" in corpo and "NIF: 987654321" in corpo

    def test_sem_segundo_titular_nao_ha_seccao(self):
        assert "2.º titular" not in prefill.bloco_dados_do_cliente(PROCESSO)

    def test_campos_vazios_ficam_de_fora_sem_na(self):
        corpo = prefill.bloco_dados_do_cliente({"client_name": "Ana"})
        assert "N/A" not in corpo and "NIF" not in corpo

    @pytest.mark.asyncio
    async def test_index_nao_tem_rascunho(self, fake_async_db):
        fake_async_db.processes.docs.append(dict(PROCESSO))
        with patch.object(prefill, "db", fake_async_db):
            with pytest.raises(HTTPException) as e:
                await prefill.run_compose_prefill("p-1", _user("indexacao"))
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_consultor_recebe_assunto_corpo_e_empresa(self, fake_async_db):
        fake_async_db.processes.docs.append({**PROCESSO, "company_id": "c-power"})
        with patch.object(prefill, "db", fake_async_db):
            r = await prefill.run_compose_prefill("p-1", _user("consultor"))
        assert r["subject"] == "Processo #1234 — Ana Silva"
        assert "NIF: 123456789" in r["body"]
        assert r["company_id"] == "c-power" and r["process_id"] == "p-1"

    @pytest.mark.asyncio
    async def test_processo_apagado_nao_da_rascunho(self, fake_async_db):
        fake_async_db.processes.docs.append({**PROCESSO, "is_deleted": True})
        with patch.object(prefill, "db", fake_async_db):
            with pytest.raises(HTTPException) as e:
                await prefill.run_compose_prefill("p-1", _user("consultor"))
        assert e.value.status_code == 404


# ── 5a: modelos por empresa, só a Direção altera, apagar é lógico ─────────────
class _Req:
    def __init__(self, company_id):
        self.headers = {"x-company-id": company_id} if company_id else {}


async def _empresa(company_id):
    return company_id


class TestModelos:
    def test_a_listagem_e_da_empresa_activa_e_dos_gerais_e_nunca_apagados(self):
        q = modelos.condicao_dos_modelos_visiveis("c-1")
        assert {"is_deleted": {"$ne": True}} in q["$and"]
        ramos = q["$and"][1]["$or"]
        assert {"company_id": "c-1"} in ramos
        assert {"company_id": "c-2"} not in ramos

    def test_sem_empresa_activa_so_os_gerais(self):
        ramos = modelos.condicao_dos_modelos_visiveis(None)["$and"][1]["$or"]
        assert all(r.get("company_id") in (None, "", "default") or "$exists" in str(r) for r in ramos)

    @pytest.mark.parametrize("papel", ["consultor", "intermediario", "administrativo", "indexacao"])
    def test_so_a_direcao_altera_modelos(self, papel):
        with pytest.raises(HTTPException) as e:
            modelos.exigir_quem_gere_modelos(_user(papel))
        assert e.value.status_code == 403

    @pytest.mark.parametrize("papel", ["master", "admin", "ceo", "diretor"])
    def test_a_direcao_pode(self, papel):
        modelos.exigir_quem_gere_modelos(_user(papel))

    @pytest.mark.asyncio
    async def test_apagar_e_logico(self, fake_async_db):
        fake_async_db.email_templates.docs.append({"id": "t-1", "company_id": "c-1", "name": "x"})
        with patch.object(modelos, "db", fake_async_db), \
                patch.object(modelos, "_empresa_activa", lambda r, u: _empresa("c-1")):
            await modelos.run_delete_email_template("t-1", _user("ceo"), request=_Req("c-1"))
        doc = fake_async_db.email_templates.docs[0]
        assert doc["is_deleted"] is True and doc["status"] == "eliminado"

    @pytest.mark.asyncio
    async def test_nao_se_apaga_o_modelo_de_outra_empresa(self, fake_async_db):
        fake_async_db.email_templates.docs.append({"id": "t-1", "company_id": "c-2", "name": "x"})
        with patch.object(modelos, "db", fake_async_db), \
                patch.object(modelos, "_empresa_activa", lambda r, u: _empresa("c-1")):
            with pytest.raises(HTTPException) as e:
                await modelos.run_delete_email_template("t-1", _user("ceo"), request=_Req("c-1"))
        assert e.value.status_code == 404
        assert not fake_async_db.email_templates.docs[0].get("is_deleted")

    @pytest.mark.asyncio
    async def test_o_master_altera_de_qualquer_empresa(self, fake_async_db):
        fake_async_db.email_templates.docs.append({"id": "t-1", "company_id": "c-2", "name": "x"})
        with patch.object(modelos, "db", fake_async_db), \
                patch.object(modelos, "_empresa_activa", lambda r, u: _empresa("c-1")):
            await modelos.run_delete_email_template("t-1", _user("master"), request=_Req("c-1"))
        assert fake_async_db.email_templates.docs[0]["is_deleted"] is True

    def test_variaveis_do_processo_no_modelo(self):
        texto = "Olá {cliente}, NIF {p1_nif}, processo {process_number}. {desconhecida}"
        r = modelos.preencher_modelo(texto, {"cliente": "Ana", "p1_nif": "123", "process_number": 7})
        assert r == "Olá Ana, NIF 123, processo 7. {desconhecida}"


# ── 7a: apagar só na própria caixa ─────────────────────────────────────────────
class TestApagarSoNaPropriaCaixa:
    def test_email_da_caixa_de_outro_nao_se_apaga(self):
        with pytest.raises(HTTPException) as e:
            crud.exigir_email_da_propria_caixa({"synced_for_user": "u-2"}, _user("ceo", "u-1"))
        assert e.value.status_code == 403

    def test_o_dono_apaga(self):
        crud.exigir_email_da_propria_caixa({"synced_for_user": "u-1"}, _user("consultor", "u-1"))

    def test_caixas_partilhadas_seguem_as_regras_de_sempre(self):
        crud.exigir_email_da_propria_caixa({"account": "shared"}, _user("consultor", "u-1"))

    @pytest.mark.asyncio
    async def test_o_apagar_recusa_antes_de_tocar_no_imap(self, fake_async_db):
        fake_async_db.emails.docs.append({"id": "e-1", "synced_for_user": "u-2", "message_id": "<m>"})
        with patch.object(crud, "db", fake_async_db), \
                patch.object(crud, "imap_move_to_trash") as imap:
            with pytest.raises(HTTPException):
                await crud.run_delete_email("e-1", _user("ceo", "u-1"))
        imap.assert_not_called()
        assert not fake_async_db.emails.docs[0].get("is_archived")


# ── 12a: o Index só consulta ───────────────────────────────────────────────────
class TestIndexSoConsulta:
    @pytest.mark.asyncio
    async def test_index_nao_desassocia(self, fake_async_db):
        fake_async_db.emails.docs.append({"id": "e-1", "process_id": "p-1"})
        with patch.object(crud, "db", fake_async_db):
            with pytest.raises(HTTPException) as e:
                await crud.run_disassociate_email({"email_id": "e-1"}, _user("indexacao"))
        assert e.value.status_code == 403
        assert fake_async_db.emails.docs[0]["process_id"] == "p-1"


# ── 11a: etiqueta curta no assunto ─────────────────────────────────────────────
class TestEtiquetaCurta:
    def test_formato(self):
        assert etiqueta_numerica(1234) == "[Ref: #1234]"
        assert etiqueta_numerica(None) is None and etiqueta_numerica("abc") is None

    @pytest.mark.asyncio
    async def test_o_envio_usa_o_numero_e_sem_numero_o_uuid(self, fake_async_db):
        fake_async_db.processes.docs.extend([{"id": "p-1", "process_number": 1234}, {"id": "p-2"}])
        assert await etiqueta_curta_do_processo(fake_async_db, "p-1") == "[Ref: #1234]"
        assert await etiqueta_curta_do_processo(fake_async_db, "p-2") == "[Ref: #p-2]"

    def test_nao_se_etiqueta_duas_vezes_com_o_numero(self):
        assert assunto_tem_a_etiqueta("Re: x [Ref: #1234]", "p-1", 1234)
        assert not assunto_tem_a_etiqueta("Re: x [Ref: #1235]", "p-1", 1234)

    def test_le_se_o_numero(self):
        assert extrair_id_da_etiqueta("Re: Processo #1234 — Ana [Ref: #1234]") == "1234"

    @pytest.mark.asyncio
    async def test_numero_liga_quando_o_email_e_do_cliente(self, fake_async_db):
        fake_async_db.processes.docs.append(dict(PROCESSO))
        r = await processo_da_etiqueta(fake_async_db, "Re: [Ref: #1234]", ["Ana <ANA@exemplo.pt>"])
        assert r == "p-1"

    @pytest.mark.asyncio
    async def test_numero_adivinhado_por_um_estranho_nao_liga(self, fake_async_db):
        fake_async_db.processes.docs.append(dict(PROCESSO))
        assert await processo_da_etiqueta(fake_async_db, "[Ref: #1234]", ["intruso@mau.pt"]) is None
        assert await processo_da_etiqueta(fake_async_db, "[Ref: #1234]") is None

    @pytest.mark.asyncio
    async def test_numero_repetido_e_ambiguo(self, fake_async_db):
        fake_async_db.processes.docs.extend([dict(PROCESSO), {**PROCESSO, "id": "p-9"}])
        assert await processo_da_etiqueta(fake_async_db, "[Ref: #1234]", ["ana@exemplo.pt"]) is None

    @pytest.mark.asyncio
    async def test_numero_de_processo_apagado_nao_liga(self, fake_async_db):
        fake_async_db.processes.docs.append({**PROCESSO, "is_deleted": True})
        assert await processo_da_etiqueta(fake_async_db, "[Ref: #1234]", ["ana@exemplo.pt"]) is None

    @pytest.mark.asyncio
    async def test_a_etiqueta_antiga_do_uuid_continua_a_ligar(self, fake_async_db):
        fake_async_db.processes.docs.append(dict(PROCESSO))
        assert await processo_da_etiqueta(fake_async_db, "[Ref: #p-1]") == "p-1"
