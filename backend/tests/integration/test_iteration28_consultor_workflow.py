"""
====================================================================
Iteration 28: Testes do Workflow do Consultor
====================================================================
Funcionalidades testadas:
1. Login como consultor (flaviosilva@powerealestate.pt)
2. Listar processos como consultor
3. Ver detalhes de processo específico
4. Adicionar link Drive a um processo (POST /api/onedrive/links/{process_id})
5. Listar links de um processo (GET /api/onedrive/links/{process_id})
6. Criar novo processo como consultor (POST /api/processes/create-client)
7. Verificar atribuição automática do consultor ao processo criado
====================================================================
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Credenciais de teste conforme especificado
CONSULTOR_EMAIL = "flaviosilva@powerealestate.pt"
CONSULTOR_PASSWORD = "flavio123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin"


@pytest.fixture(scope="module")
def consultor_session():
    """Session autenticada como consultor."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login como consultor
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": CONSULTOR_EMAIL,
        "password": CONSULTOR_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Falha no login consultor: {response.status_code} - {response.text}")
    
    data = response.json()
    token = data.get("access_token") or data.get("token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    session.consultor_data = data.get("user", data)
    return session


@pytest.fixture(scope="module")
def admin_session():
    """Session autenticada como admin para operações auxiliares."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Falha no login admin: {response.status_code} - {response.text}")
    
    data = response.json()
    token = data.get("access_token") or data.get("token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestConsultorLogin:
    """Testes de autenticação do consultor."""
    
    def test_01_consultor_login_success(self):
        """1. Login como consultor com credenciais válidas."""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": CONSULTOR_EMAIL,
            "password": CONSULTOR_PASSWORD
        })
        
        assert response.status_code == 200, f"Login falhou: {response.text}"
        data = response.json()
        
        # Verificar estrutura da resposta
        assert "access_token" in data or "token" in data, "Token não retornado"
        
        # Verificar dados do utilizador
        user = data.get("user", data)
        assert user.get("email") == CONSULTOR_EMAIL, "Email não coincide"
        assert user.get("role") == "consultor", f"Role incorreto: {user.get('role')}"
        print(f"✅ Login consultor: {user.get('name')} (role: {user.get('role')})")
    
    def test_02_consultor_login_invalid_password(self):
        """Login com senha incorreta deve falhar."""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": CONSULTOR_EMAIL,
            "password": "senhaerrada"
        })
        
        assert response.status_code in [401, 400], f"Deveria falhar: {response.status_code}"
        print("✅ Login com senha errada rejeitado correctamente")


class TestConsultorListarProcessos:
    """Testes de listagem de processos para consultor."""
    
    def test_03_listar_processos_consultor(self, consultor_session):
        """2. Listar processos como consultor - deve ver processos atribuídos."""
        response = consultor_session.get(f"{BASE_URL}/api/processes")
        
        assert response.status_code == 200, f"Erro ao listar processos: {response.text}"
        processes = response.json()
        
        # Consultor pode ter 0 ou mais processos atribuídos
        assert isinstance(processes, list), "Resposta deve ser uma lista"
        print(f"✅ Consultor tem {len(processes)} processos atribuídos")
        
        # Se houver processos, verificar estrutura
        if processes:
            first = processes[0]
            assert "id" in first, "Processo deve ter id"
            assert "client_name" in first or "client_email" in first, "Processo deve ter dados do cliente"
            print(f"  → Exemplo: {first.get('client_name', 'N/A')} - Status: {first.get('status', 'N/A')}")
        
        return processes
    
    def test_04_listar_meus_clientes(self, consultor_session):
        """Listar clientes usando endpoint /my-clients."""
        response = consultor_session.get(f"{BASE_URL}/api/processes/my-clients")
        
        assert response.status_code == 200, f"Erro ao listar clientes: {response.text}"
        data = response.json()
        
        assert "clients" in data, "Resposta deve conter 'clients'"
        assert "total" in data, "Resposta deve conter 'total'"
        
        print(f"✅ /my-clients retorna {data.get('total', 0)} clientes")
        return data


class TestConsultorVerDetalhesProcesso:
    """Testes de visualização de detalhes de processo."""
    
    def test_05_ver_detalhes_processo(self, consultor_session, admin_session):
        """3. Ver detalhes de um processo específico."""
        # Primeiro obter lista de processos (como admin para garantir que existe)
        response = admin_session.get(f"{BASE_URL}/api/processes")
        assert response.status_code == 200
        processes = response.json()
        
        if not processes:
            pytest.skip("Nenhum processo disponível para testar")
        
        # Pegar primeiro processo
        process_id = processes[0]["id"]
        
        # Tentar ver detalhes como consultor
        # Nota: Pode falhar se o processo não estiver atribuído ao consultor
        response = consultor_session.get(f"{BASE_URL}/api/processes/{process_id}")
        
        # Consultor pode ver se estiver atribuído ou se for processo público
        if response.status_code == 200:
            data = response.json()
            assert data.get("id") == process_id, "ID do processo não coincide"
            print(f"✅ Detalhes do processo {process_id[:8]}... obtidos")
            print(f"  → Cliente: {data.get('client_name', 'N/A')}")
            print(f"  → Status: {data.get('status', 'N/A')}")
        elif response.status_code == 403:
            print(f"⚠️ Consultor não tem acesso ao processo {process_id[:8]}... (esperado se não atribuído)")
        else:
            pytest.fail(f"Erro inesperado: {response.status_code} - {response.text}")


class TestOneDriveLinks:
    """Testes dos endpoints de links OneDrive/Drive."""
    
    # Variável de classe para guardar o process_id criado
    _created_process_id = None
    
    @pytest.fixture
    def test_process_id(self, consultor_session):
        """Obter um processo válido para testes de links - reutiliza o mesmo processo."""
        if TestOneDriveLinks._created_process_id is None:
            # Criar um processo de teste para garantir acesso
            process_data = {
                "process_type": "credito_habitacao",
                "client_name": "TEST_Process_Links",
                "personal_data": {
                    "nome_completo": "TEST Process Links",
                    "email": "test.links@test.com"
                }
            }
            
            response = consultor_session.post(f"{BASE_URL}/api/processes/create-client", json=process_data)
            if response.status_code != 200:
                pytest.skip(f"Não foi possível criar processo de teste: {response.text}")
            
            TestOneDriveLinks._created_process_id = response.json()["id"]
        
        return TestOneDriveLinks._created_process_id
    
    def test_06_listar_links_processo(self, consultor_session, test_process_id):
        """5. Listar links de um processo (GET /api/onedrive/links/{process_id})."""
        response = consultor_session.get(f"{BASE_URL}/api/onedrive/links/{test_process_id}")
        
        assert response.status_code == 200, f"Erro ao listar links: {response.text}"
        links = response.json()
        
        assert isinstance(links, list), "Resposta deve ser uma lista"
        print(f"✅ Processo {test_process_id[:8]}... tem {len(links)} links")
        
        return links
    
    def test_07_adicionar_link_drive(self, consultor_session, test_process_id):
        """4. Adicionar link Drive a um processo (POST /api/onedrive/links/{process_id})."""
        link_data = {
            "name": "TEST_Documentos_Teste",
            "url": "https://drive.google.com/drive/folders/test123",
            "description": "Link de teste - pode ser eliminado"
        }
        
        response = consultor_session.post(
            f"{BASE_URL}/api/onedrive/links/{test_process_id}",
            json=link_data
        )
        
        assert response.status_code == 200, f"Erro ao adicionar link: {response.text}"
        result = response.json()
        
        # Verificar estrutura da resposta
        assert "id" in result, "Link deve ter ID"
        assert result.get("name") == link_data["name"], "Nome não coincide"
        assert result.get("url") == link_data["url"], "URL não coincide"
        
        print(f"✅ Link adicionado com sucesso: {result.get('id')}")
        
        # Guardar ID para limpeza
        return result.get("id")
    
    def test_08_verificar_link_adicionado(self, consultor_session, test_process_id):
        """Verificar que o link foi persistido."""
        # Primeiro adicionar um link
        link_data = {
            "name": "TEST_Verificacao_Link",
            "url": "https://1drv.ms/f/test-verification",
            "description": "Link para verificação de persistência"
        }
        
        add_response = consultor_session.post(
            f"{BASE_URL}/api/onedrive/links/{test_process_id}",
            json=link_data
        )
        assert add_response.status_code == 200
        link_id = add_response.json().get("id")
        
        # Agora verificar se está na lista
        list_response = consultor_session.get(f"{BASE_URL}/api/onedrive/links/{test_process_id}")
        assert list_response.status_code == 200
        
        links = list_response.json()
        link_ids = [l.get("id") for l in links]
        
        assert link_id in link_ids, "Link adicionado não encontrado na lista"
        print(f"✅ Link {link_id} persistido e verificado na lista")
        
        return link_id
    
    def test_09_remover_link(self, consultor_session, test_process_id):
        """Remover link de um processo."""
        # Primeiro adicionar um link para remover
        link_data = {
            "name": "TEST_Link_Para_Remover",
            "url": "https://s3://bucket/test-delete",
            "description": "Este link será removido"
        }
        
        add_response = consultor_session.post(
            f"{BASE_URL}/api/onedrive/links/{test_process_id}",
            json=link_data
        )
        assert add_response.status_code == 200
        link_id = add_response.json().get("id")
        
        # Remover o link
        delete_response = consultor_session.delete(
            f"{BASE_URL}/api/onedrive/links/{test_process_id}/{link_id}"
        )
        
        assert delete_response.status_code == 200, f"Erro ao remover link: {delete_response.text}"
        result = delete_response.json()
        assert result.get("success") == True, "Remoção não confirmada"
        
        print(f"✅ Link {link_id} removido com sucesso")
        
        # Verificar que foi removido
        list_response = consultor_session.get(f"{BASE_URL}/api/onedrive/links/{test_process_id}")
        links = list_response.json()
        link_ids = [l.get("id") for l in links]
        
        assert link_id not in link_ids, "Link ainda existe após remoção"
        print(f"✅ Link confirmado removido da lista")
    
    def test_10_adicionar_link_url_invalido(self, consultor_session, test_process_id):
        """Adicionar link com URL inválido deve falhar."""
        link_data = {
            "name": "Link Inválido",
            "url": "not-a-valid-url",
            "description": "Este deve falhar"
        }
        
        response = consultor_session.post(
            f"{BASE_URL}/api/onedrive/links/{test_process_id}",
            json=link_data
        )
        
        assert response.status_code == 400, f"Deveria rejeitar URL inválido: {response.status_code}"
        print("✅ URL inválido rejeitado correctamente")


class TestConsultorCriarProcesso:
    """Testes de criação de processo por consultor."""
    
    def test_11_criar_processo_como_consultor(self, consultor_session):
        """6. Criar novo processo como consultor (POST /api/processes/create-client)."""
        process_data = {
            "process_type": "credito_habitacao",
            "client_name": "TEST_Cliente_Consultor_Teste",
            "client_email": "test.cliente.consultor@test.com",
            "personal_data": {
                "nome_completo": "TEST Cliente Consultor Teste",
                "email": "test.cliente.consultor@test.com",
                "telefone": "912345678"
            }
        }
        
        response = consultor_session.post(
            f"{BASE_URL}/api/processes/create-client",
            json=process_data
        )
        
        assert response.status_code == 200, f"Erro ao criar processo: {response.text}"
        result = response.json()
        
        # Verificar estrutura do processo criado
        assert "id" in result, "Processo deve ter ID"
        # client_name vem do personal_data.nome_completo ou do client_name direto
        assert "TEST" in result.get("client_name", ""), f"Nome do cliente incorreto: {result.get('client_name')}"
        assert result.get("process_type") == "credito_habitacao", "Tipo de processo incorreto"
        
        print(f"✅ Processo criado: {result.get('id')}")
        print(f"  → Cliente: {result.get('client_name')}")
        print(f"  → Tipo: {result.get('process_type')}")
        print(f"  → Status: {result.get('status')}")
        
        return result
    
    def test_12_verificar_atribuicao_automatica(self, consultor_session):
        """7. Verificar atribuição automática do consultor ao processo criado."""
        # Criar novo processo
        process_data = {
            "process_type": "credito_habitacao",
            "client_name": "TEST_Cliente_Atribuicao",
            "client_email": "test.atribuicao@test.com",
            "personal_data": {
                "nome_completo": "TEST Cliente Atribuicao",
                "email": "test.atribuicao@test.com"
            }
        }
        
        response = consultor_session.post(
            f"{BASE_URL}/api/processes/create-client",
            json=process_data
        )
        
        assert response.status_code == 200, f"Erro ao criar processo: {response.text}"
        result = response.json()
        
        # Verificar atribuição automática
        consultor_id = consultor_session.consultor_data.get("id")
        consultor_name = consultor_session.consultor_data.get("name")
        
        assigned_consultor_id = result.get("assigned_consultor_id")
        assigned_consultor_name = result.get("consultor_name")
        
        assert assigned_consultor_id == consultor_id, \
            f"Consultor não atribuído automaticamente. Esperado: {consultor_id}, Obtido: {assigned_consultor_id}"
        
        print(f"✅ Atribuição automática confirmada:")
        print(f"  → Consultor ID: {assigned_consultor_id}")
        print(f"  → Consultor Nome: {assigned_consultor_name}")
        
        return result


class TestCleanup:
    """Limpeza de dados de teste."""
    
    def test_99_cleanup_test_data(self, admin_session):
        """Limpar processos e links de teste criados."""
        # Buscar processos de teste
        response = admin_session.get(f"{BASE_URL}/api/processes")
        if response.status_code != 200:
            print("⚠️ Não foi possível buscar processos para limpeza")
            return
        
        processes = response.json()
        test_processes = [p for p in processes if p.get("client_name", "").startswith("TEST_")]
        
        cleaned = 0
        for process in test_processes:
            process_id = process["id"]
            
            # Limpar links de teste deste processo
            links_response = admin_session.get(f"{BASE_URL}/api/onedrive/links/{process_id}")
            if links_response.status_code == 200:
                links = links_response.json()
                for link in links:
                    if link.get("name", "").startswith("TEST_"):
                        admin_session.delete(f"{BASE_URL}/api/onedrive/links/{process_id}/{link['id']}")
            
            cleaned += 1
        
        print(f"✅ Limpeza: {cleaned} processos de teste identificados")
        print("  → Links TEST_ removidos dos processos")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
