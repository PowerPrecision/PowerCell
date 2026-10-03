"""Ligar um email à ficha do cliente (Lote 7, ponto 4).

A pergunta da auditoria era «o sistema liga as mensagens recebidas, pelo
endereço, à ficha do respectivo cliente?». A resposta era **não, na caixa que
mais importa**: a sincronização da caixa PESSOAL de cada consultor — a que o
worker corre de 10 em 10 minutos — não resolvia por endereço nenhum. Só herdava
o processo do email-pai de uma conversa e lia a etiqueta `[Proc-xxx]` do
assunto, e eram esses dois caminhos a funcionar que escondiam o terceiro em
falta.

E a que resolvia (as contas partilhadas) conhecia **só** `client_email` e
`monitored_emails`: o 2.º titular, que é co-mutuário, nunca ligava.

O teste mais importante deste ficheiro é
`test_as_DUAS_direccoes_da_relacao_conhecem_os_mesmos_campos`.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services.email_client_match import (
    CAMPOS_DE_ENDERECO_DO_PROCESSO,
    MOTIVO_MONITORIZADO,
    MOTIVO_SEGUNDO_TITULAR,
    MOTIVO_TITULAR,
    construir_condicao,
    motivo_do_processo,
    normalizar_enderecos,
    resolver_processo_por_endereco,
)


async def _semear(fake_db, *, estados=("analise",)):
    await fake_db.workflow_statuses.insert_one(
        {"name": "analise", "label": "Análise", "order": 1})
    await fake_db.workflow_statuses.insert_one(
        {"name": "concluido", "label": "Concluído", "order": 9,
         "is_final": True})


class TestANormalizacao:
    def test_minusculas_sem_espacos_sem_duplicados(self):
        assert normalizar_enderecos(
            ["  Ana@Exemplo.PT ", "ana@exemplo.pt", "", None, "rui@x.pt"]
        ) == ["ana@exemplo.pt", "rui@x.pt"]

    def test_sem_enderecos_a_condicao_e_None_e_nao_um_dicionario_vazio(self):
        """Um `{}` casaria com o PRIMEIRO processo da colecção.

        É exactamente a forma de defeito que esta função vem fechar.
        """
        for vazio in ([], None, ["", "   "]):
            assert construir_condicao(vazio) is None


class TestOsCampos:
    def test_a_condicao_cobre_os_tres_campos(self):
        condicao = construir_condicao(["ana@exemplo.pt"])
        campos = {list(ramo.keys())[0] for ramo in condicao["$or"]}
        assert campos == {
            "client_email", "monitored_emails", "titular2_data.email",
        }

    def test_as_DUAS_direccoes_da_relacao_conhecem_os_mesmos_campos(self):
        """O teste que explica porque é que o 2.º titular não ligava.

        `collect_emails_from_process_doc` vai do PROCESSO para os endereços
        (serve a listagem de emails de um processo) e conhecia
        `titular2_data.email` desde sempre. O sentido inverso — endereço →
        processo — era uma consulta escrita à mão que só conhecia dois campos.
        **As duas direcções da mesma relação tinham conjuntos de campos
        diferentes, e só a menos usada estava certa.**

        O oráculo é a função de PRODUÇÃO, nunca uma terceira lista.
        """
        from services.email_process_crud import collect_emails_from_process_doc

        processo = {
            "client_email": "titular1@exemplo.pt",
            "monitored_emails": ["monitorizado@exemplo.pt"],
            "titular2_data": {"email": "titular2@exemplo.pt"},
        }
        pelo_inverso = collect_emails_from_process_doc(processo)

        # Cada endereço que o inverso conhece tem de ser alcançável por um
        # ramo da condição que este módulo constrói.
        condicao = construir_condicao(pelo_inverso)
        campos_da_condicao = {list(r.keys())[0] for r in condicao["$or"]}
        assert campos_da_condicao == set(CAMPOS_DE_ENDERECO_DO_PROCESSO)
        assert pelo_inverso == {
            "titular1@exemplo.pt",
            "monitorizado@exemplo.pt",
            "titular2@exemplo.pt",
        }


class TestOMotivo:
    @pytest.mark.parametrize("endereco,esperado", [
        ("titular1@exemplo.pt", MOTIVO_TITULAR),
        ("titular2@exemplo.pt", MOTIVO_SEGUNDO_TITULAR),
        ("monitorizado@exemplo.pt", MOTIVO_MONITORIZADO),
    ])
    def test_diz_por_que_campo_casou(self, endereco, esperado):
        """Sem isto, diagnosticar uma ligação errada obriga a refazer a
        consulta à mão — é a razão do `source` no `resolve_sending_account`.
        """
        processo = {
            "id": "p1",
            "client_email": "titular1@exemplo.pt",
            "monitored_emails": ["monitorizado@exemplo.pt"],
            "titular2_data": {"email": "titular2@exemplo.pt"},
        }
        assert motivo_do_processo(processo, [endereco]) == esperado


class TestAResolucao:
    @pytest.mark.asyncio
    async def test_liga_pelo_endereco_do_TITULAR_1(self, fake_async_db):
        from services import email_client_match

        await _semear(fake_async_db)
        await fake_async_db.processes.insert_one({
            "id": "p1", "status": "analise",
            "client_email": "ana@exemplo.pt",
        })
        with patch.object(email_client_match, "db", fake_async_db):
            r = await resolver_processo_por_endereco(["ana@exemplo.pt"])
        assert r.process_id == "p1"
        assert r.motivo == MOTIVO_TITULAR

    @pytest.mark.asyncio
    async def test_liga_pelo_endereco_do_2o_TITULAR(self, fake_async_db):
        """O defeito principal: o co-mutuário escreve e nada acontecia."""
        from services import email_client_match

        await _semear(fake_async_db)
        await fake_async_db.processes.insert_one({
            "id": "p1", "status": "analise",
            "client_email": "ana@exemplo.pt",
            "titular2_data": {"email": "rui@exemplo.pt"},
        })
        with patch.object(email_client_match, "db", fake_async_db):
            r = await resolver_processo_por_endereco(["rui@exemplo.pt"])
        assert r.process_id == "p1"
        assert r.motivo == MOTIVO_SEGUNDO_TITULAR

    @pytest.mark.asyncio
    async def test_liga_por_um_endereco_MONITORIZADO(self, fake_async_db):
        from services import email_client_match

        await _semear(fake_async_db)
        await fake_async_db.processes.insert_one({
            "id": "p1", "status": "analise",
            "client_email": "ana@exemplo.pt",
            "monitored_emails": ["advogado@exemplo.pt"],
        })
        with patch.object(email_client_match, "db", fake_async_db):
            r = await resolver_processo_por_endereco(["advogado@exemplo.pt"])
        assert r.process_id == "p1"

    @pytest.mark.asyncio
    async def test_DOIS_candidatos_dao_AMBIGUO_e_o_email_fica_geral(
        self, fake_async_db,
    ):
        """«Não encontrei» e «encontrei dois» são respostas diferentes.

        O `find_one` antigo ficava com o que o Mongo calhasse devolver, de
        forma permanente — e o email entrava na ficha errada. É a lição do
        `run_auto_map_client_s3_folders`, aqui com dados pessoais pelo meio.
        """
        from services import email_client_match

        await _semear(fake_async_db)
        for pid in ("p1", "p2"):
            await fake_async_db.processes.insert_one({
                "id": pid, "status": "analise",
                "client_email": "ana@exemplo.pt",
            })
        with patch.object(email_client_match, "db", fake_async_db):
            r = await resolver_processo_por_endereco(["ana@exemplo.pt"])
        assert r.process_id is None
        assert r.ambiguo is True
        assert sorted(r.candidatos) == ["p1", "p2"]

    @pytest.mark.asyncio
    async def test_um_endereco_desconhecido_nao_liga_a_nada(self, fake_async_db):
        from services import email_client_match

        await _semear(fake_async_db)
        await fake_async_db.processes.insert_one({
            "id": "p1", "status": "analise", "client_email": "ana@exemplo.pt",
        })
        with patch.object(email_client_match, "db", fake_async_db):
            r = await resolver_processo_por_endereco(["estranho@exemplo.pt"])
        assert r.process_id is None
        assert r.ambiguo is False

    @pytest.mark.asyncio
    async def test_um_processo_FECHADO_nao_recebe_emails_novos(
        self, fake_async_db,
    ):
        from services import email_client_match

        await _semear(fake_async_db)
        await fake_async_db.processes.insert_one({
            "id": "p1", "status": "concluido",
            "client_email": "ana@exemplo.pt",
        })
        with patch.object(email_client_match, "db", fake_async_db):
            r = await resolver_processo_por_endereco(["ana@exemplo.pt"])
        assert r.process_id is None

    @pytest.mark.asyncio
    async def test_as_fases_terminais_vem_do_MOTOR_e_nao_de_uma_lista_a_mao(
        self, fake_async_db,
    ):
        """A lista antiga era `["concluido", "cancelado", "arquivado"]`.

        Inclui o typo legado `arquivado` e **não** o valor canónico `arquivo`
        (a D-6 com outro nome), e uma fase nova fechada pelo administrador
        também não entrava.
        """
        from services import email_client_match

        from services import workflow_phases

        # A verdade de "fase terminada" é `is_active: False` no motor (ver
        # `nomes_terminais`), e o `workflow_phases` tem a SUA referência ao
        # proxy — patchar só o `email_client_match` deixava-o a ler o real.
        await fake_async_db.workflow_statuses.insert_one({
            "name": "desistencia_nova", "label": "Desistência",
            "order": 10, "is_active": False,
        })
        await fake_async_db.processes.insert_one({
            "id": "p1", "status": "desistencia_nova",
            "client_email": "ana@exemplo.pt",
        })
        with patch.object(email_client_match, "db", fake_async_db), \
             patch.object(workflow_phases, "db", fake_async_db):
            r = await resolver_processo_por_endereco(["ana@exemplo.pt"])
        assert r.process_id is None, (
            "uma fase fechada pelo administrador tem de fechar a associação"
        )

    @pytest.mark.asyncio
    async def test_a_REDE_limita_a_associacao(self, fake_async_db):
        """Sem isto, um email entrava na ficha de um cliente de outra rede."""
        from services import email_client_match

        await _semear(fake_async_db)
        await fake_async_db.processes.insert_one({
            "id": "p-domus", "status": "analise",
            "client_email": "ana@exemplo.pt", "network_id": "domus",
        })
        with patch.object(email_client_match, "db", fake_async_db):
            r = await resolver_processo_por_endereco(
                ["ana@exemplo.pt"], network_id="grupo_power_precision",
            )
        assert r.process_id is None

    @pytest.mark.asyncio
    async def test_sem_rede_a_unicidade_vale_sobre_o_sistema_INTEIRO(
        self, fake_async_db,
    ):
        """A ausência de rede é mais estrita, não menos.

        Dois candidatos em redes diferentes dão ambíguo e o email fica geral,
        em vez de entrar num deles em silêncio.
        """
        from services import email_client_match

        await _semear(fake_async_db)
        await fake_async_db.processes.insert_one({
            "id": "p-power", "status": "analise",
            "client_email": "ana@exemplo.pt", "network_id": "power",
        })
        await fake_async_db.processes.insert_one({
            "id": "p-domus", "status": "analise",
            "client_email": "ana@exemplo.pt", "network_id": "domus",
        })
        with patch.object(email_client_match, "db", fake_async_db):
            r = await resolver_processo_por_endereco(["ana@exemplo.pt"])
        assert r.ambiguo is True

    @pytest.mark.asyncio
    async def test_sem_enderecos_nao_consulta_nada(self, fake_async_db):
        """Contraprova de que a condição `None` chega até aqui."""
        from services import email_client_match

        class _Explode:
            def __getattr__(self, _nome):
                raise AssertionError("consultou a BD sem endereços")

        with patch.object(email_client_match, "db", _Explode()):
            r = await resolver_processo_por_endereco([])
        assert r.process_id is None

    @pytest.mark.asyncio
    async def test_uma_falha_de_leitura_nao_liga_nada_e_nao_propaga(
        self, fake_async_db,
    ):
        """Falha FECHADA: sem resposta, o email fica geral.

        Levantar aqui faria uma sincronização inteira falhar por causa de um
        soluço na associação, que é a parte menos importante dela.
        """
        from services import email_client_match

        class _Falha:
            class processes:
                @staticmethod
                def find(*_a, **_k):
                    raise RuntimeError("Mongo em baixo")

        with patch.object(email_client_match, "db", _Falha()):
            r = await resolver_processo_por_endereco(["ana@exemplo.pt"])
        assert r.process_id is None
        assert r.ambiguo is False


class TestALigacaoNosDoisSincronizadores:
    """Guardas: as DUAS sincronizações têm de usar o ponto único."""

    def _fonte(self):
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        caminho = (
            Path(__file__).resolve().parents[2] / "services" / "email_service.py"
        )
        return codigo_sem_comentarios(caminho.read_text(encoding="utf-8"))

    def test_as_duas_sincronizacoes_chamam_o_resolvedor(self):
        """DUAS chamadas: as contas partilhadas E a caixa pessoal.

        Uma só significa que a caixa pessoal voltou a ficar sem associação
        por endereço — o defeito principal deste ponto.
        """
        assert self._fonte().count("resolver_processo_por_endereco(") == 2

    def test_nao_resta_a_consulta_escrita_a_mao(self):
        fonte = self._fonte()
        assert '"monitored_emails": {"$in"' not in fonte
        assert "'monitored_emails': {'$in'" not in fonte

    def test_nao_resta_a_lista_de_estados_escrita_a_mao(self):
        fonte = self._fonte()
        assert '"concluido", "cancelado", "arquivado"' not in fonte
        assert "'concluido', 'cancelado', 'arquivado'" not in fonte
