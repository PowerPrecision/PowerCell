"""
Testes unitários — os alertas não atravessam redes (Lote 6, ponto 8).

DOIS DEFEITOS
=============
1. `services/alerts.py` recolhia a gestão com
   `deep_role_in_filter(["admin","ceo","diretor"])` e **zero** condições de
   tenant, em três sítios. Um alerta de um processo da Power notificava a
   direcção da Domus — com o NOME DO CLIENTE no título. O varrimento do
   Lote 4/5 não o apanhou porque não é uma listagem: é um emissor, e o
   inventário foi feito do lado de quem LISTA.
2. Os atribuídos eram lidos de uma lista escrita à mão que ignorava os
   PLURAIS (`assigned_consultor_ids`): num processo com dois consultores,
   o segundo nunca era notificado.

O teste da contraprova (`test_o_atribuido_recebe_sempre`) é o que impede a
correcção de virar regressão: "não notificar ninguém" satisfaz o teste da
fuga e é pior do que a fuga.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services import alert_audience as aa
from services.process_staff_assignment import build_set_consultor_fields


REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "ilha_domus"


@pytest.fixture
def db_com_duas_redes(fake_async_db):
    fake_async_db.companies.docs.extend([
        {"id": "c-power", "name": "Power", "network_id": REDE_POWER},
        {"id": "c-prec", "name": "Precision", "network_id": REDE_POWER},
        {"id": "c-domus", "name": "Domus", "network_id": REDE_DOMUS},
    ])
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "dir-power", "company_id": "c-power", "role": "diretor"},
        {"user_id": "ceo-prec", "company_id": "c-prec", "role": "ceo"},
        {"user_id": "dir-domus", "company_id": "c-domus", "role": "diretor"},
        {"user_id": "consultor-power", "company_id": "c-power", "role": "consultor"},
    ])
    return fake_async_db


class TestOsAtribuidos:
    def test_le_os_PLURAIS_e_nao_so_o_primeiro(self):
        """O defeito 2: o segundo consultor nunca era notificado."""
        processo = build_set_consultor_fields(["u-1", "u-2"], ["Ana", "Rui"])
        assert aa.ids_atribuidos(processo) == ["u-1", "u-2"]

    def test_apanha_a_pilha_antiga_que_so_tem_singulares(self):
        processo = {"consultant_id": "u-legado"}
        assert aa.ids_atribuidos(processo) == ["u-legado"]

    def test_nao_repete_quem_aparece_em_varios_campos(self):
        processo = build_set_consultor_fields(["u-1"], ["Ana"])
        assert aa.ids_atribuidos(processo).count("u-1") == 1

    def test_assigned_to_escalar_da_pilha_antiga(self):
        """O `assigned_to` nem sempre é lista (Lote 4, ponto 12)."""
        assert aa.ids_atribuidos({"assigned_to": "u-9"}) == ["u-9"]

    def test_um_processo_vazio_nao_inventa_ninguem(self):
        assert aa.ids_atribuidos({}) == []
        assert aa.ids_atribuidos(None) == []

    def test_os_campos_vem_das_constantes_de_producao(self):
        """Contraprova: uma lista à mão divergiria do `set`/`clear`."""
        from services.process_staff_assignment import (
            CONSULTOR_ID_FIELDS,
            MEDIADOR_ID_FIELDS,
        )

        for campo in (*CONSULTOR_ID_FIELDS, *MEDIADOR_ID_FIELDS):
            assert campo in aa.CAMPOS_SINGULARES, f"{campo} ficou de fora"


class TestAFugaEntreRedes:
    @pytest.mark.asyncio
    async def test_a_direccao_da_domus_NAO_e_notificada_de_um_processo_da_power(
        self, db_com_duas_redes,
    ):
        processo = {"id": "p-1", "network_id": REDE_POWER}
        with patch.object(aa, "db", db_com_duas_redes):
            gestao = await aa.gestao_da_rede_do_processo(
                processo, ["admin", "ceo", "diretor"],
            )
        assert set(gestao) == {"dir-power", "ceo-prec"}
        assert "dir-domus" not in gestao

    @pytest.mark.asyncio
    async def test_a_power_ve_a_precision_porque_partilham_a_rede(
        self, db_com_duas_redes,
    ):
        """Contraprova: um filtro por EMPRESA cortaria as duas."""
        processo = {"id": "p-1", "network_id": REDE_POWER}
        with patch.object(aa, "db", db_com_duas_redes):
            gestao = await aa.gestao_da_rede_do_processo(processo, ["ceo"])
        assert gestao == ["ceo-prec"]

    @pytest.mark.asyncio
    async def test_so_os_papeis_pedidos(self, db_com_duas_redes):
        processo = {"id": "p-1", "network_id": REDE_POWER}
        with patch.object(aa, "db", db_com_duas_redes):
            gestao = await aa.gestao_da_rede_do_processo(processo, ["diretor"])
        assert gestao == ["dir-power"]
        assert "consultor-power" not in gestao


class TestSemCarimbo:
    @pytest.mark.asyncio
    async def test_a_empresa_do_processo_resolve_a_rede(self, db_com_duas_redes):
        processo = {"id": "p-1", "company_id": "c-domus"}
        with patch.object(aa, "db", db_com_duas_redes):
            gestao = await aa.gestao_da_rede_do_processo(processo, ["diretor"])
        assert gestao == ["dir-domus"]

    @pytest.mark.asyncio
    async def test_sem_rede_determinavel_NAO_notifica_ninguem(self, db_com_duas_redes):
        """Falha fechada.

        A alternativa é difundir o nome de um cliente a toda a gestão de
        todas as redes. Um alerta que não chega nota-se; uma fuga não.
        """
        processo = {"id": "p-orfao"}
        with patch.object(aa, "db", db_com_duas_redes), \
             patch.object(aa, "rede_de_omissao", return_value=None):
            gestao = await aa.gestao_da_rede_do_processo(processo, ["diretor"])
        assert gestao == []

    @pytest.mark.asyncio
    async def test_a_rede_de_omissao_cobre_a_pilha_por_carimbar(
        self, db_com_duas_redes,
    ):
        processo = {"id": "p-antigo"}
        with patch.object(aa, "db", db_com_duas_redes), \
             patch.object(aa, "rede_de_omissao", return_value=REDE_POWER):
            gestao = await aa.gestao_da_rede_do_processo(processo, ["diretor"])
        assert gestao == ["dir-power"]


class TestDestinatariosDoAlerta:
    @pytest.mark.asyncio
    async def test_o_atribuido_recebe_SEMPRE(self, db_com_duas_redes):
        """A contraprova que impede a correcção de virar regressão.

        Sem ela, "não notificar ninguém" passa o teste da fuga — e um
        alerta que não chega a quem trata do processo é pior do que o
        problema que se foi corrigir.
        """
        processo = {
            "id": "p-1",
            "network_id": REDE_POWER,
            **build_set_consultor_fields(["consultor-power"], ["Ana"]),
        }
        with patch.object(aa, "db", db_com_duas_redes):
            destinatarios = await aa.destinatarios_do_alerta(
                processo, papeis_de_gestao=["diretor"],
            )
        assert "consultor-power" in destinatarios
        assert "dir-power" in destinatarios
        assert "dir-domus" not in destinatarios

    @pytest.mark.asyncio
    async def test_o_atribuido_recebe_mesmo_sem_rede_determinavel(
        self, db_com_duas_redes,
    ):
        """Estar atribuído é, por si, a autorização.

        O filtro de rede é para a audiência obtida por CARGO; aplicá-lo
        também aos atribuídos faria um processo por carimbar deixar de
        avisar o próprio consultor que trata dele.
        """
        processo = {"id": "p-orfao", "consultant_id": "u-legado"}
        with patch.object(aa, "db", db_com_duas_redes), \
             patch.object(aa, "rede_de_omissao", return_value=None):
            destinatarios = await aa.destinatarios_do_alerta(
                processo, papeis_de_gestao=["diretor"],
            )
        assert destinatarios == ["u-legado"]

    @pytest.mark.asyncio
    async def test_sem_papeis_de_gestao_so_os_atribuidos(self, db_com_duas_redes):
        processo = {"id": "p-1", "network_id": REDE_POWER, "consultor_id": "u-1"}
        with patch.object(aa, "db", db_com_duas_redes):
            destinatarios = await aa.destinatarios_do_alerta(processo)
        assert destinatarios == ["u-1"]


class TestGuardaDeFonte:
    """`alerts.py` pede a audiência ao ponto único, e não a reconstrói.

    Toda a guarda sobre o código-fonte precisa da CONTRAPROVA ao lado —
    sem ela, apagar a chamada satisfaz o guarda.
    """

    @staticmethod
    def _codigo_dos_alertas() -> str:
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        caminho = Path(__file__).resolve().parents[2] / "services" / "alerts.py"
        return codigo_sem_comentarios(caminho.read_text(encoding="utf-8"))

    def test_chama_o_ponto_unico(self):
        codigo = self._codigo_dos_alertas()
        assert "destinatarios_do_alerta" in codigo
        assert "gestao_da_rede_do_processo" in codigo
        assert "ids_atribuidos" in codigo

    def test_nao_resta_nenhum_leque_de_gestao_sem_filtro_de_rede(self):
        """A contraprova da correcção.

        `deep_role_in_filter` não é proibido em si — é uma função legítima.
        O que não pode voltar é uma consulta a `db.users` por CARGO dentro
        de `alerts.py`, porque é essa que não tem como saber a rede do
        processo. A leitura ignora comentários, senão a explicação do
        defeito fazia o teste ficar vermelho e a saída óbvia seria apagar
        a explicação.
        """
        codigo = self._codigo_dos_alertas()
        assert "deep_role_in_filter" not in codigo, (
            "voltou uma consulta por cargo a `alerts.py`: usar "
            "`alert_audience.gestao_da_rede_do_processo`, que conhece a rede."
        )

    def test_a_notificacao_do_registo_leva_destinatario(self):
        """Lote 5, ponto 3 — `run_get_notifications` filtra SÓ por `user_id`.

        Um documento sem esse campo é invisível a toda a gente, e foi assim
        que a notificação de registo de cliente deixou de aparecer sem
        ninguém dar por isso.
        """
        # O `ast.unparse` normaliza as aspas (AGENTS.md, guardas de fonte):
        # comparar sem elas, senão a asserção testa o estilo de citação.
        codigo = self._codigo_dos_alertas().replace('"', "'")
        assert "'user_id': admin['id']" in codigo
