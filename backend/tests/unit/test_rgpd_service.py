"""
Testes unitários para services.rgpd_service — resolução dinâmica de Empresa
(PACOTE FR-4).

Escudo de Testes Unitários: garante que ``_resolve_rgpd_company`` respeita a
prioridade documentada — primeiro tenta resolver a Empresa a partir do
processo (``process_id``), e só recorre ao utilizador (``user``/``user_id``)
quando o processo não tem nenhuma empresa associada válida.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services import rgpd_service


class TestResolveRgpdCompanyPriorities:
    @pytest.mark.asyncio
    async def test_resolve_rgpd_company_priorities(self):
        """
        Prova as duas metades da prioridade de resolução documentada em
        ``_resolve_rgpd_company``:

        1. Tenta SEMPRE obter a empresa a partir do ``process_id`` primeiro
           (consulta ``db.processes`` antes de tocar em ``db.users``).
        2. Quando o candidato do processo não corresponde a nenhuma empresa
           real em ``db.companies``, cai para o candidato do ``user_id``
           (só aí consulta ``db.users``) e devolve essa empresa.
        """
        call_order: list[str] = []

        async def fake_process_find_one(*args, **kwargs):
            call_order.append("process")
            # Processo tem uma empresa associada, mas essa empresa não
            # existe (ou já não existe) em db.companies.
            return {
                "company_id": "empresa-sem-registo",
                "company_name": None,
                "company": None,
            }

        async def fake_user_find_one(*args, **kwargs):
            call_order.append("user")
            return {
                "active_company_id": "empresa-user",
                "company_id": None,
                "company": None,
            }

        async def fake_companies_find_one(query, *args, **kwargs):
            call_order.append(f"company:{query}")
            if query.get("id") == "empresa-user":
                return {"id": "empresa-user", "name": "Empresa do Utilizador"}
            return None

        mock_db = MagicMock()
        mock_db.processes.find_one = AsyncMock(side_effect=fake_process_find_one)
        mock_db.users.find_one = AsyncMock(side_effect=fake_user_find_one)
        mock_db.companies.find_one = AsyncMock(side_effect=fake_companies_find_one)

        with patch.object(rgpd_service, "db", mock_db):
            company = await rgpd_service._resolve_rgpd_company(
                process_id="proc-1", user_id="user-1",
            )

        # 1) O processo é sempre consultado antes do utilizador.
        assert call_order.index("process") < call_order.index("user")
        mock_db.processes.find_one.assert_awaited_once_with(
            {"id": "proc-1"},
            {"_id": 0, "company_id": 1, "company_name": 1, "company": 1},
        )

        # 2) Como o candidato do processo ("empresa-sem-registo") não
        #    corresponde a nenhuma empresa real, o utilizador é consultado.
        mock_db.users.find_one.assert_awaited_once_with(
            {"id": "user-1"},
            {"_id": 0, "company": 1, "active_company_id": 1, "company_id": 1},
        )

        # O resultado final é a empresa encontrada pelo caminho do utilizador.
        assert company == {"id": "empresa-user", "name": "Empresa do Utilizador"}

    @pytest.mark.asyncio
    async def test_resolve_rgpd_company_skips_further_lookups_when_process_resolves(self):
        """
        Complemento da prioridade acima: quando o candidato do processo já
        corresponde a uma empresa real em ``db.companies``, o ciclo de
        resolução pára logo aí — nunca chega a tentar o candidato do
        utilizador em ``db.companies`` (a empresa do processo tem sempre
        prioridade absoluta sobre a do utilizador).
        """
        mock_db = MagicMock()
        mock_db.processes.find_one = AsyncMock(
            return_value={
                "company_id": "empresa-processo",
                "company_name": None,
                "company": None,
            }
        )
        mock_db.users.find_one = AsyncMock(return_value={"active_company_id": "empresa-user"})
        mock_db.companies.find_one = AsyncMock(
            return_value={"id": "empresa-processo", "name": "Empresa do Processo"}
        )

        with patch.object(rgpd_service, "db", mock_db):
            company = await rgpd_service._resolve_rgpd_company(
                process_id="proc-1", user_id="user-1",
            )

        assert company == {"id": "empresa-processo", "name": "Empresa do Processo"}
        mock_db.processes.find_one.assert_awaited_once()
        # A empresa do processo resolveu logo ao primeiro candidato — a
        # única chamada a db.companies é pelo candidato do processo,
        # nunca chega a tentar "empresa-user".
        mock_db.companies.find_one.assert_awaited_once_with(
            {"id": "empresa-processo"}, {"_id": 0}
        )

    @pytest.mark.asyncio
    async def test_resolve_rgpd_company_returns_none_when_nothing_matches(self):
        """Nunca levanta excepção — devolve ``None`` quando nada corresponde."""
        mock_db = MagicMock()
        mock_db.processes.find_one = AsyncMock(return_value=None)
        mock_db.users.find_one = AsyncMock(return_value=None)
        mock_db.companies.find_one = AsyncMock(return_value=None)

        with patch.object(rgpd_service, "db", mock_db):
            company = await rgpd_service._resolve_rgpd_company(
                process_id="proc-1", user_id="user-1",
            )

        assert company is None
