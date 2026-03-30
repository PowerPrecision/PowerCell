"""
Script de Seed - Popular base de dados com dados iniciais
=========================================================
Cria utilizadores, configurações e dados de exemplo.
"""
import asyncio
import hashlib
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

# Connection string
MONGO_URL = "mongodb+srv://admin:y8aEj7BByvgeO2zO@cluster0.373e1eh.mongodb.net/?appName=Cluster0&retryWrites=true&w=majority"
DB_NAME = "powercell_dev"


def hash_password(password: str) -> str:
    """Hash password com SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


async def seed_database():
    """Popular base de dados com dados iniciais."""
    
    print("🔌 A conectar ao MongoDB Atlas...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    try:
        # Testar conexão
        await client.admin.command('ping')
        print("✅ Conexão estabelecida!")
        
        # ============================================
        # 1. CRIAR UTILIZADORES
        # ============================================
        print("\n👥 A criar utilizadores...")
        
        users = [
            {
                "id": "user-admin-001",
                "email": "admin@sistema.pt",
                "password": hash_password("admin"),
                "name": "Administrador",
                "role": "admin",
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            {
                "id": "user-consultor-001",
                "email": "consultor@sistema.pt",
                "password": hash_password("consultor123"),
                "name": "João Consultor",
                "role": "consultor",
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        ]
        
        # Limpar e inserir utilizadores
        await db.users.delete_many({})
        result = await db.users.insert_many(users)
        print(f"   ✅ {len(result.inserted_ids)} utilizadores criados")
        
        # ============================================
        # 2. CRIAR CONFIGURAÇÕES DO SISTEMA
        # ============================================
        print("\n⚙️  A criar configurações...")
        
        system_config = {
            "id": "system-config",
            "app_name": "PowerCell",
            "company_name": "PowerCell",
            "default_language": "pt",
            "timezone": "Europe/Lisbon",
            "email_notifications": True,
            "auto_backup_enabled": False,
            "backup_frequency": "daily",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.system_config.delete_many({})
        await db.system_config.insert_one(system_config)
        print("   ✅ Configurações do sistema criadas")
        
        # ============================================
        # 3. CRIAR CONFIGURAÇÕES DE IA
        # ============================================
        print("\n🤖 A criar configurações de IA...")
        
        ai_config = {
            "id": "ai-config",
            "models": {
                "gemini_flash": {
                    "key": "gemini_flash",
                    "name": "Gemini 2.0 Flash",
                    "provider": "gemini",
                    "model_id": "gemini-2.0-flash-exp",
                    "is_active": True,
                    "cost_per_1k_input": 0.075,
                    "cost_per_1k_output": 0.30
                },
                "gpt4o_mini": {
                    "key": "gpt4o_mini",
                    "name": "GPT-4o Mini",
                    "provider": "openai",
                    "model_id": "gpt-4o-mini",
                    "is_active": True,
                    "cost_per_1k_input": 0.15,
                    "cost_per_1k_output": 0.60
                }
            },
            "task_defaults": {
                "scraper_extraction": "gemini_flash",
                "document_analysis": "gpt4o_mini",
                "weekly_report": "gemini_flash",
                "error_analysis": "gemini_flash"
            },
            "cache_settings": {
                "cache_limit": 1000,
                "notify_at_percentage": 80
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.ai_config.delete_many({})
        await db.ai_config.insert_one(ai_config)
        print("   ✅ Configurações de IA criadas")
        
        # ============================================
        # 4. CRIAR STATUS DE PROCESSOS
        # ============================================
        print("\n📋 A criar status de processos...")
        
        statuses = [
            {"id": "triagem", "name": "Triagem", "order": 1, "color": "#6B7280"},
            {"id": "documentacao", "name": "Documentação", "order": 2, "color": "#F59E0B"},
            {"id": "analise", "name": "Análise", "order": 3, "color": "#3B82F6"},
            {"id": "aprovado", "name": "Aprovado", "order": 4, "color": "#10B981"},
            {"id": "recusado", "name": "Recusado", "order": 5, "color": "#EF4444"},
            {"id": "concluido", "name": "Concluído", "order": 6, "color": "#8B5CF6"},
            {"id": "desistido", "name": "Desistido", "order": 7, "color": "#9CA3AF"},
            {"id": "cancelado", "name": "Cancelado", "order": 8, "color": "#374151"}
        ]
        
        await db.process_statuses.delete_many({})
        await db.process_statuses.insert_many(statuses)
        print(f"   ✅ {len(statuses)} status criados")
        
        # ============================================
        # 5. CRIAR CATEGORIAS DE DOCUMENTOS
        # ============================================
        print("\n📁 A criar categorias de documentos...")
        
        doc_categories = [
            {"id": "identificacao", "name": "Identificação", "icon": "id-card"},
            {"id": "rendimentos", "name": "Rendimentos", "icon": "money"},
            {"id": "emprego", "name": "Emprego", "icon": "briefcase"},
            {"id": "bancarios", "name": "Bancários", "icon": "bank"},
            {"id": "imovel", "name": "Imóvel", "icon": "home"},
            {"id": "contratos", "name": "Contratos", "icon": "file-text"},
            {"id": "fiscais", "name": "Fiscais", "icon": "receipt"},
            {"id": "simulacoes", "name": "Simulações", "icon": "calculator"},
            {"id": "outros", "name": "Outros", "icon": "folder"}
        ]
        
        await db.document_categories.delete_many({})
        await db.document_categories.insert_many(doc_categories)
        print(f"   ✅ {len(doc_categories)} categorias criadas")
        
        # ============================================
        # 6. CRIAR COLECÇÕES VAZIAS (índices)
        # ============================================
        print("\n📊 A criar colecções e índices...")
        
        # Criar colecções se não existirem
        collections_to_create = [
            "processes",
            "clients", 
            "documents",
            "notifications",
            "emails",
            "timeline_events",
            "import_sessions",
            "import_errors",
            "background_jobs",
            "nif_mappings",
            "backup_history"
        ]
        
        existing = await db.list_collection_names()
        for col in collections_to_create:
            if col not in existing:
                await db.create_collection(col)
        
        # Criar índices importantes
        await db.users.create_index("email", unique=True)
        await db.processes.create_index("client_name")
        await db.processes.create_index("status")
        await db.documents.create_index("process_id")
        await db.notifications.create_index([("user_id", 1), ("is_read", 1)])
        
        print(f"   ✅ Colecções e índices criados")
        
        # ============================================
        # RESUMO FINAL
        # ============================================
        print("\n" + "="*50)
        print("🎉 BASE DE DADOS INICIALIZADA COM SUCESSO!")
        print("="*50)
        
        collections = await db.list_collection_names()
        print(f"\n📦 Total de colecções: {len(collections)}")
        
        print("\n👤 Utilizadores criados:")
        print("   • admin@sistema.pt / admin (Administrador)")
        print("   • powerprecision@sistema.pt / PowerCell (Gestor)")
        print("   • consultor@sistema.pt / consultor123 (Consultor)")
        
        print("\n✅ Pronto a usar!")
        
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(seed_database())
