"""PORTAL DO PARCEIRO — o parceiro escreve notas no seu processo.

O ataque, escrito primeiro: a nota só pode entrar num processo que é DESTE parceiro (relação ∧ rede
activa); para um id alheio, de outra rede, eliminado ou inexistente a resposta é a MESMA (404). Uma lead
não tem equipa a ler, um processo fechado não se altera, e o corpo não escolhe nem o autor nem a origem.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE, tenant_db  # noqa: F401
from tests.unit.test_parceiro_leitura import (  # noqa: F401  (fixtures e cenários partilhados)
    PT1,
    PT2,
    _dono,
    mundo,
    rede_de_omissao_incumbente,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def com_notas(mundo):
    import services.partner_notes as pn
    import services.partner_portal_read as ppr
    from services import workflow_phases

    with tenant_db(mundo, ppr, pn, workflow_phases):
        _dono(mundo)
        yield mundo


def _processo(db, pid="a-novo"):
    return next(p for p in db.processes.docs if p["id"] == pid)


async def _escrever(texto="Cliente já tem o IRS", parceiro=PT1, caso="a-novo"):
    from services.partner_notes import PartnerNoteIn, run_partner_add_note

    return await run_partner_add_note(parceiro, caso, PartnerNoteIn(text=texto))


class TestAExploracao:
    @pytest.mark.parametrize("caso", ["x-de-outro-parceiro", "x-rede-errada", "x-eliminado", "x-sem-parceiro", "t-da-domus", "nao-existe"])
    async def test_nao_se_escreve_num_caso_que_nao_e_meu(self, com_notas, caso):
        antes = [dict(p) for p in com_notas.processes.docs]
        with pytest.raises(HTTPException) as exc:
            await _escrever(caso=caso)
        assert exc.value.status_code == 404
        assert com_notas.processes.docs == antes, "uma recusa não pode deixar rasto"

    async def test_alheio_e_inexistente_respondem_o_mesmo(self, com_notas):
        with pytest.raises(HTTPException) as alheio:
            await _escrever(caso="x-de-outro-parceiro")
        with pytest.raises(HTTPException) as nada:
            await _escrever(caso="nao-existe")
        assert alheio.value.status_code == nada.value.status_code
        assert alheio.value.detail == nada.value.detail

    async def test_o_corpo_nao_escolhe_autor_nem_origem(self):
        from services.partner_notes import PartnerNoteIn

        for campo in ({"partner_id": "pt-2"}, {"user_id": "u1"}, {"origem": "equipa"}, {"user_name": "Diretor"}):
            with pytest.raises(ValidationError):
                PartnerNoteIn(text="olá", **campo)


class TestEscrever:
    async def test_o_dono_escreve_e_a_nota_entra_no_feed_da_equipa(self, com_notas):
        r = await _escrever("Cliente já tem o IRS")
        nota = _processo(com_notas)["observation_notes"][-1]
        assert nota["text"] == "Cliente já tem o IRS"
        assert nota["origem"] == "parceiro" and nota["partner_id"] == "pt-1"
        assert nota["user_name"] == "Rui"
        assert nota["user_id"] is None, "o id do parceiro nunca se escreve onde o CRM espera um utilizador"
        assert r["nota"]["e_minha"] is True and r["nota"]["do_parceiro"] is True

    async def test_a_equipa_le_a_nota_no_cartao_observacoes(self, com_notas):
        from services.process_observation_notes import coalesce_observation_notes

        await _escrever("Cliente já tem o IRS")
        textos = [n["text"] for n in coalesce_observation_notes(_processo(com_notas))]
        assert "Cliente já tem o IRS" in textos

    async def test_o_texto_legado_nao_se_perde_ao_nascer_o_feed(self, com_notas):
        """Com `observation_notes` vazio e um escalar legado, o feed nasce COM o legado (senão o CRM, que
        só lê o feed quando não está vazio, deixava de mostrar a nota antiga)."""
        from services.process_observation_notes import coalesce_observation_notes

        proc = _processo(com_notas)
        proc.pop("observation_notes", None)
        proc["observations"] = "Nota antiga da consultora"
        await _escrever("Nota nova do parceiro")
        textos = [n["text"] for n in coalesce_observation_notes(_processo(com_notas))]
        assert "Nota antiga da consultora" in textos and "Nota nova do parceiro" in textos

    async def test_nao_mexe_nas_notas_escalares_do_consultor(self, com_notas):
        proc = _processo(com_notas)
        antes = (proc["notes"], proc["observations"])
        await _escrever("Outra nota")
        assert (proc["notes"], proc["observations"]) == antes

    async def test_o_parceiro_ve_a_sua_nota_marcada_e_a_da_equipa_nao(self, com_notas):
        import services.partner_portal_read as ppr

        _processo(com_notas)["observation_notes"] = [
            {"id": "n1", "text": "Da equipa", "created_at": "2026-10-03T10:00:00+00:00",
             "user_id": "USER-1", "user_name": "Carla"},
        ]
        await _escrever("Minha nota")
        caso = await ppr.run_get_case(PT1, "a-novo")
        por_texto = {n["text"]: n for n in caso["notas_da_equipa"]}
        assert por_texto["Minha nota"]["e_minha"] is True and por_texto["Minha nota"]["do_parceiro"] is True
        assert por_texto["Da equipa"]["e_minha"] is False and por_texto["Da equipa"]["do_parceiro"] is False
        assert "pt-1" not in repr(caso) or "partner_id" not in repr(caso["notas_da_equipa"])

    async def test_a_nota_de_um_parceiro_nao_e_minha_para_outro(self):
        from services.partner_visibility import notas_da_equipa

        proc = {"observation_notes": [
            {"id": "n", "text": "x", "created_at": "2026-10-03", "user_name": "Sara", "origem": "parceiro", "partner_id": "pt-2"},
        ]}
        [nota] = notas_da_equipa(proc, "pt-1")
        assert nota["do_parceiro"] is True and nota["e_minha"] is False
        assert "pt-2" not in repr(nota), "o id de outro parceiro nunca sai"


class TestRecusas:
    async def test_numa_lead_nao_ha_notas(self, com_notas):
        with pytest.raises(HTTPException) as exc:
            await _escrever(caso="lead-1")
        assert exc.value.status_code == 409

    async def test_um_processo_fechado_nao_aceita_notas(self, com_notas):
        antes = list(_processo(com_notas, "d-escriturado").get("observation_notes") or [])
        with pytest.raises(HTTPException) as exc:
            await _escrever(caso="d-escriturado")
        assert exc.value.status_code == 409
        assert list(_processo(com_notas, "d-escriturado").get("observation_notes") or []) == antes

    async def test_contraprova_o_processo_aberto_aceita(self, com_notas):
        await _escrever(caso="b-analise")
        assert _processo(com_notas, "b-analise")["observation_notes"][-1]["text"] == "Cliente já tem o IRS"

    async def test_o_feed_cheio_recusa(self, com_notas):
        from services.partner_notes import MAX_NOTAS_NO_PROCESSO

        _processo(com_notas)["observation_notes"] = [
            {"id": f"n{i}", "text": f"t{i}", "created_at": "2026-10-03", "user_name": "x"}
            for i in range(MAX_NOTAS_NO_PROCESSO)
        ]
        with pytest.raises(HTTPException) as exc:
            await _escrever()
        assert exc.value.status_code == 409


class TestTexto:
    @pytest.mark.parametrize("texto", ["", "   ", "\n\t"])
    async def test_vazio_nao_entra(self, texto):
        from services.partner_notes import PartnerNoteIn

        with pytest.raises(ValidationError):
            PartnerNoteIn(text=texto)

    async def test_so_etiquetas_ficam_vazias_e_sao_recusadas(self, com_notas):
        with pytest.raises(HTTPException) as exc:
            await _escrever("<b></b><i> </i>")
        assert exc.value.status_code == 400

    def test_o_html_e_o_controlo_saem(self):
        from services.partner_notes import limpar_texto_da_nota

        assert limpar_texto_da_nota("Olá <script>alert(1)</script>mundo\x00\x07") == "Olá alert(1)mundo"
        assert limpar_texto_da_nota("a\r\n\r\n\r\n\r\nb") == "a\n\nb"
        assert limpar_texto_da_nota(None) == ""

    async def test_tem_tecto(self):
        from services.partner_notes import PartnerNoteIn
        from services.partner_visibility import MAX_CARACTERES_DA_NOTA

        PartnerNoteIn(text="x" * MAX_CARACTERES_DA_NOTA)
        with pytest.raises(ValidationError):
            PartnerNoteIn(text="x" * (MAX_CARACTERES_DA_NOTA + 1))


class TestConcorrencia:
    async def test_se_o_feed_mudou_repete_sem_perder_a_outra_nota(self, com_notas):
        """A equipa escreveu entre a leitura e a escrita: a escrita optimista falha, relê e acrescenta."""
        import services.partner_notes as pn

        original = pn._gravar
        chamadas = {"n": 0}

        async def _com_corrida(process_id, processo, nota):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                _processo(com_notas)["observation_notes"] = [
                    {"id": "equipa", "text": "A equipa escreveu primeiro", "created_at": "2026-10-04", "user_name": "Carla"},
                ]
                return False
            return await original(process_id, processo, nota)

        with patch.object(pn, "_gravar", _com_corrida):
            await _escrever("Nota do parceiro")
        textos = [n["text"] for n in _processo(com_notas)["observation_notes"]]
        assert "A equipa escreveu primeiro" in textos and "Nota do parceiro" in textos
        assert chamadas["n"] == 2

    async def test_a_escrita_optimista_realmente_recusa_um_feed_desactualizado(self, com_notas):
        """Sem isto o teste acima passava com uma escrita às cegas."""
        import services.partner_notes as pn

        proc = dict(_processo(com_notas))
        proc["observation_notes"] = [{"id": "velho", "text": "v", "created_at": "2026-10-01", "user_name": "x"}]
        nota = pn.construir_nota_do_parceiro("nova", PT1)
        assert await pn._gravar("a-novo", proc, nota) is False  # o documento real tem outro feed

    async def test_corridas_sem_fim_dao_409_e_nao_gravam(self, com_notas):
        import services.partner_notes as pn

        with patch.object(pn, "_gravar", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await _escrever()
        assert exc.value.status_code == 409


class TestEfeitos:
    async def test_o_historico_e_o_aviso_a_equipa_atribuida(self, com_notas):
        _processo(com_notas)["assigned_consultor_ids"] = ["u-ana"]
        avisos = AsyncMock()
        registos = AsyncMock()
        with patch("services.realtime_notifications.send_realtime_notification", avisos), \
                patch("services.history.log_history", registos):
            await _escrever("Há novidades")
        registos.assert_awaited_once()
        assert registos.await_args.args[2] == "Parceiro adicionou nota"
        assert registos.await_args.args[1]["id"] == "partner:pt-1"
        destinatarios = [c.kwargs["user_id"] for c in avisos.await_args_list]
        assert destinatarios == ["u-ana"], "só a equipa: o parceiro atribuído não é um utilizador"
        assert "Há novidades" not in repr(avisos.await_args), "o texto da nota não vai na notificação"

    async def test_um_efeito_que_falha_nao_deita_abaixo_a_nota(self, com_notas):
        with patch("services.history.log_history", AsyncMock(side_effect=RuntimeError("boom"))), \
                patch("services.realtime_notifications.send_realtime_notification", AsyncMock(side_effect=RuntimeError("boom"))):
            r = await _escrever("Ainda assim fica")
        assert r["success"] is True
        assert _processo(com_notas)["observation_notes"][-1]["text"] == "Ainda assim fica"


class TestForma:
    def test_a_rota_e_do_plano_do_parceiro_limitada_e_com_response(self):
        import ast
        import pathlib

        fonte = (pathlib.Path(__file__).resolve().parents[2] / "routes" / "partner_portal.py").read_text(encoding="utf-8")
        funcao = next(
            n for n in ast.walk(ast.parse(fonte))
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "partner_add_note"
        )
        texto = ast.unparse(funcao)
        assert "get_current_partner" in texto
        assert "limiter.limit" in texto
        assert "response: Response" in texto

    def test_o_servico_nao_escreve_nos_escalares_do_consultor(self):
        import inspect

        from services import partner_notes
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        corpo = codigo_da_funcao_sem_comentarios(partner_notes._gravar)
        assert "observation_notes" in corpo  # contraprova: leu o sítio certo
        assert "'observations'" not in corpo and "'notes'" not in corpo
        assert inspect.iscoroutinefunction(partner_notes._gravar)
