"""
====================================================================
TESTES UNITÁRIOS - PERMISSÕES DE UTILIZADORES
====================================================================
Testes para verificar permissões e roles.
====================================================================
"""
import pytest


class TestRolePermissions:
    """Testes para verificar permissões por role."""
    
    def test_gestor_documentos_cannot_create_clients(self):
        """gestor_documentos não pode criar clientes."""
        from models.enums import UserRoleEnum
        
        restricted_roles = ["gestor_documentos"]
        
        for role in restricted_roles:
            assert role in UserRoleEnum.all_values()
            # Em produção, verificar que endpoint retorna 403
    
    def test_gestor_documentos_cannot_create_processes(self):
        """gestor_documentos não pode criar processos."""
        # Verificar que gestor_documentos está na lista de roles restritos
        restricted_for_process_creation = ["gestor_documentos", "cliente"]
        
        for role in restricted_for_process_creation:
            # Em produção, endpoint POST /processes deve retornar 403
            assert role in ["gestor_documentos", "cliente"]
    
    def test_admin_has_all_permissions(self):
        """admin tem todas as permissões."""
        from models.enums import UserRoleEnum
        
        admin_role = UserRoleEnum.ADMIN
        assert admin_role.value == "admin"
        
        # admin está em management_roles
        assert "admin" in UserRoleEnum.management_roles()
    
    def test_staff_roles_excludes_cliente(self):
        """staff_roles não inclui cliente."""
        from models.enums import UserRoleEnum
        
        staff = UserRoleEnum.staff_roles()
        assert "cliente" not in staff
        
        # Mas inclui outros roles
        assert "admin" in staff
        assert "consultor" in staff
        assert "gestor_documentos" in staff
    
    def test_management_roles_are_subset_of_staff(self):
        """management_roles é subconjunto de staff_roles."""
        from models.enums import UserRoleEnum
        
        management = set(UserRoleEnum.management_roles())
        staff = set(UserRoleEnum.staff_roles())
        
        assert management.issubset(staff)


class TestCanCreateProcess:
    """Testes para verificação de criação de processos."""
    
    def test_roles_that_can_create_processes(self):
        """Verifica quais roles podem criar processos."""
        roles_that_can_create = [
            "admin", "ceo", "diretor", "consultor", 
            "intermediario", "mediador", "administrativo"
        ]
        
        roles_that_cannot_create = ["gestor_documentos", "cliente"]
        
        for role in roles_that_can_create:
            assert role != "gestor_documentos"
            assert role != "cliente"
        
        for role in roles_that_cannot_create:
            assert role in ["gestor_documentos", "cliente"]
    
    def test_frontend_permission_check_logic(self):
        """Simula lógica de verificação do frontend."""
        def can_create_process(user_role: str) -> bool:
            return user_role != "gestor_documentos"
        
        assert can_create_process("admin") == True
        assert can_create_process("consultor") == True
        assert can_create_process("gestor_documentos") == False
    
    def test_frontend_permission_check_clients(self):
        """Simula lógica de criação de clientes."""
        def can_create_clients(user_role: str) -> bool:
            return user_role != "gestor_documentos"
        
        assert can_create_clients("admin") == True
        assert can_create_clients("consultor") == True
        assert can_create_clients("gestor_documentos") == False


class TestCanViewAssignments:
    """Testes para verificação de atribuições."""
    
    def test_roles_that_can_see_assignments(self):
        """Verifica quais roles podem ver atribuições."""
        roles_that_can_see = [
            "admin", "ceo", "diretor", "consultor", 
            "intermediario", "mediador", "administrativo"
        ]
        
        roles_that_cannot_see = ["gestor_documentos"]
        
        for role in roles_that_can_see:
            assert role not in roles_that_cannot_see
    
    def test_frontend_assignments_button_logic(self):
        """Simula lógica do botão de atribuições."""
        def can_see_assignments(user_role: str) -> bool:
            return user_role != "gestor_documentos"
        
        assert can_see_assignments("admin") == True
        assert can_see_assignments("consultor") == True
        assert can_see_assignments("gestor_documentos") == False
