"""As capacidades resolvem-se pelo papel EFECTIVO (Lote 6, ponto 3).

O BOTÃO FANTASMA
================
O registo canónico (`models/permissions.ROLE_CAPABILITY_DEFAULTS`) já diz que o
perfil `indexacao` NÃO cria processos (`PROCESS_CREATE: False`). O ecrã não o
consultava: o botão "Novo Processo" aparecia a todos e quem não podia descobria
pelo erro.

E a resolução que existia tinha um defeito mais fundo: `resolve_capability` lê
`user["role"]` — o cargo do JWT —, enquanto a porta do servidor
(`require_roles`) usa o cargo EFECTIVO. Quem tem perfil base de consultor e
entra COMO diretor era avaliado como consultor. É a forma do
`history._is_stealth_user` e do botão de eliminar cliente: **duas noções de
papel no mesmo caminho dão as duas respostas erradas.**
"""
from __future__ import annotations

import pytest

from models.permissions import CAPABILITIES
from services.capability_gate import (
    capacidades_do_papel,
    capacidades_por_papel,
    tem_capacidade,
)

CONSULTOR_QUE_E_DIRETOR = {
    "id": "u1",
    "role": "consultor",
    "additional_roles": ["diretor"],
}
INDEXADOR = {"id": "u2", "role": "indexacao"}


class TestOPapelEfectivoManda:
    def test_o_indexador_NAO_cria_processos(self):
        assert tem_capacidade(INDEXADOR, "PROCESS_CREATE") is False

    def test_o_consultor_cria_processos(self):
        assert tem_capacidade({"id": "u", "role": "consultor"}, "PROCESS_CREATE") is True

    def test_entrar_COMO_diretor_usa_as_capacidades_de_diretor(self):
        """O defeito original: era avaliado pelo cargo do JWT."""
        base = tem_capacidade(CONSULTOR_QUE_E_DIRETOR, "PROCESS_EXPORT")
        como_diretor = tem_capacidade(
            CONSULTOR_QUE_E_DIRETOR, "PROCESS_EXPORT", papel="diretor"
        )
        assert como_diretor is True
        # Contraprova de que o teste mede algo: as duas respostas diferem.
        assert base is not como_diretor

    def test_o_admin_tem_bypass(self):
        assert tem_capacidade({"id": "a", "role": "admin"}, "PROCESS_DELETE") is True

    def test_sem_utilizador_ou_sem_capacidade_recusa(self):
        assert tem_capacidade(None, "PROCESS_CREATE") is False
        assert tem_capacidade(INDEXADOR, "") is False

    def test_uma_capacidade_DESCONHECIDA_recusa(self):
        # Falha fechada: um nome com uma gralha não pode abrir um botão.
        assert tem_capacidade({"id": "u", "role": "consultor"}, "PROCESS_CRIAR") is False


class TestOsOverridesPessoaisSobrevivemAoChapeu:
    def test_um_override_do_utilizador_vence_a_default_do_papel(self):
        user = {
            "id": "u3",
            "role": "consultor",
            "permissions": {"capabilities": {"PROCESS_EXPORT": True}},
        }
        assert tem_capacidade(user, "PROCESS_EXPORT", papel="consultor") is True

    def test_o_override_acompanha_a_troca_de_papel(self):
        """O override é do UTILIZADOR, não do cargo: é o que faz uma excepção
        concedida a uma pessoa continuar a valer quando ela troca de chapéu."""
        user = {
            "id": "u4",
            "role": "consultor",
            "additional_roles": ["administrativo"],
            "permissions": {"capabilities": {"PROCESS_DELETE": True}},
        }
        assert tem_capacidade(user, "PROCESS_DELETE", papel="administrativo") is True

    def test_um_override_para_uma_capacidade_INEXISTENTE_e_ignorado(self):
        user = {
            "id": "u5",
            "role": "consultor",
            "permissions": {"capabilities": {"CAPACIDADE_QUE_JA_NAO_EXISTE": True}},
        }
        caps = capacidades_do_papel(user, "consultor")
        assert "CAPACIDADE_QUE_JA_NAO_EXISTE" not in caps


class TestOMapaQueVaiParaOEcra:
    def test_um_mapa_por_cada_papel_do_utilizador(self):
        mapa = capacidades_por_papel(
            CONSULTOR_QUE_E_DIRETOR, ["consultor", "diretor"]
        )
        assert set(mapa) == {"consultor", "diretor"}
        assert mapa["consultor"]["PROCESS_CREATE"] is True

    def test_as_capacidades_sao_as_CONHECIDAS_e_nao_um_subconjunto_qualquer(self):
        mapa = capacidades_por_papel(INDEXADOR, ["indexacao"])
        # Contraprova de que o mapa não vem vazio (um mapa vazio esconderia
        # TODOS os botões e pareceria "sem permissões").
        assert mapa["indexacao"]
        assert set(mapa["indexacao"]) <= set(CAPABILITIES)

    def test_papeis_repetidos_ou_vazios_nao_sujam_o_mapa(self):
        mapa = capacidades_por_papel(INDEXADOR, ["indexacao", "indexacao", "", None])
        assert list(mapa) == ["indexacao"]


class TestARotaNaoFicaMaisLargaQueOBotao:
    @pytest.mark.asyncio
    async def test_a_dependencia_recusa_quem_nao_tem_a_capacidade(self):
        from unittest.mock import AsyncMock, patch

        from fastapi import HTTPException

        from services import capability_gate as mod

        dependencia = mod.exigir_capacidade("PROCESS_CREATE")
        with patch("services.auth.get_effective_role_async", AsyncMock(return_value="indexacao")):
            with pytest.raises(HTTPException) as e:
                await dependencia(request=object(), user=INDEXADOR)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_dependencia_deixa_passar_quem_tem(self):
        from unittest.mock import AsyncMock, patch

        from services import capability_gate as mod

        dependencia = mod.exigir_capacidade("PROCESS_CREATE")
        user = {"id": "u", "role": "consultor"}
        with patch("services.auth.get_effective_role_async", AsyncMock(return_value="consultor")):
            assert await dependencia(request=object(), user=user) is user

    @pytest.mark.asyncio
    async def test_o_sentinel_de_TODOS_os_perfis_nao_recusa_tudo(self):
        """`X-Active-Role: all` é um modo de FILTRAGEM de dados, não um papel.

        Sem a tradução do `authorization_role`, o sentinel chegava à resolução
        como nome de papel, não casava com nenhuma default e recusava TUDO a
        quem está em modo agregado.
        """
        from unittest.mock import AsyncMock, patch

        from services import capability_gate as mod

        dependencia = mod.exigir_capacidade("PROCESS_CREATE")
        user = {"id": "u", "role": "consultor"}
        with patch(
            "services.auth.get_effective_role_async",
            AsyncMock(return_value="__all_roles__"),
        ):
            assert await dependencia(request=object(), user=user) is user


class TestAsLigacoes:
    """Sem estas, o ponto único é decoração."""

    def test_o_auth_me_devolve_o_mapa_por_papel(self):
        import services.auth_profile_handlers as mod
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(
            open(mod.__file__, encoding="utf-8").read()
        ).replace("'", '"')
        assert '"capabilities_por_papel": capacidades_por_papel(' in fonte
        # Contraprova: inclui os papéis adicionais E os das empresas (UCR) —
        # é o UCR que o `X-Active-Role` honra, logo um mapa só com o cargo do
        # JWT esconderia botões a quem troca de chapéu.
        #
        # As asserções são sobre SUBSTRINGS curtas de propósito: o
        # `codigo_sem_comentarios` passa pelo `ast.unparse`, que além de
        # normalizar as aspas REFORMATA expressões — `(user_companies or [])`
        # perde os parênteses. Foi a terceira vez que esta normalização me
        # morde, e a lição agora é mais larga: não comparar expressões, só
        # nomes.
        assert "additional_roles" in fonte
        assert "user_companies" in fonte

    def test_a_criacao_de_processo_staff_exige_a_capacidade(self):
        """A rota não pode ficar MAIS LARGA do que o botão.

        `POST /processes/create-client` entrava com `get_current_user` — sem
        restrição nenhuma. Esconder o botão e deixar a rota aberta é o «menu e
        rotas têm de concordar» ao contrário, e foi o que o Lote 5 corrigiu no
        eliminar cliente.
        """
        import ast
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2] / "routes" / "processes.py"
        ).read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        alvo = next(
            n for n in ast.walk(arvore)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
            and n.name == "create_client_process"
        )
        corpo = ast.unparse(alvo).replace("'", '"')
        assert 'exigir_capacidade("PROCESS_CREATE")' in corpo
        # Contraprova: o `get_current_user` nu já não é a porta desta rota.
        assert "Depends(get_current_user)" not in corpo
