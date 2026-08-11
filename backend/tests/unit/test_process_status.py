"""Testes unitários para services/process_status (visibilidade de pré-registo)."""
from models.auth import UserRole
from services.process_status import (
    _should_hide_pre_registo,
    PRE_REGISTO_STATUS,
    INACTIVE_STATUSES,
    ARCHIVED_STATUSES,
    LEAD_STATUS_VALUES,
)


class TestShouldHidePreRegisto:
    def test_explicit_pre_registo_filter_never_hides(self):
        # Regra 3: filtrar explicitamente por pre_registo → mostrar
        for role in [UserRole.ADMIN, UserRole.CONSULTOR, UserRole.CEO]:
            assert _should_hide_pre_registo(role, PRE_REGISTO_STATUS, None) is False

    def test_admin_hides_by_default_on_boards(self):
        # Bypass role sem search nem status → esconde (não polui quadros)
        assert _should_hide_pre_registo(UserRole.ADMIN, None, None) is True
        assert _should_hide_pre_registo(UserRole.CEO, None, "") is True

    def test_admin_searching_shows_pre_registo(self):
        # Bypass role com search ativo → mostra
        assert _should_hide_pre_registo(UserRole.ADMIN, None, "joao") is False

    def test_admin_status_filter_shows(self):
        # Bypass role com filtro de status explícito → mostra
        assert _should_hide_pre_registo(UserRole.DIRETOR, "fase_documental", None) is False

    def test_consultor_always_hides(self):
        # Não-bypass: esconde sempre (mesmo a pesquisar)
        assert _should_hide_pre_registo(UserRole.CONSULTOR, None, None) is True
        assert _should_hide_pre_registo(UserRole.CONSULTOR, None, "joao") is True

    def test_consultor_explicit_pre_registo_still_shows(self):
        # Regra 3 tem prioridade mesmo para não-bypass
        assert _should_hide_pre_registo(UserRole.CONSULTOR, PRE_REGISTO_STATUS, None) is False


class TestStatusConstants:
    def test_constants_values(self):
        assert INACTIVE_STATUSES == ["concluidos", "desistencias", "eliminados"]
        assert ARCHIVED_STATUSES == ["concluidos", "desistencias"]
        assert None in LEAD_STATUS_VALUES and PRE_REGISTO_STATUS in LEAD_STATUS_VALUES
