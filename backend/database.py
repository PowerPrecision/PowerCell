import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']

# Singleton para o cliente Motor
_client = None
_db = None


def reset_db_connection():
    """Reset da conexão (útil para testes)."""
    global _client, _db
    if _client is not None:
        try:
            _client.close()
        except:
            pass
    _client = None
    _db = None


def get_motor_client():
    """Retorna o cliente Motor (criado on-demand)."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(mongo_url)
    return _client


def get_database():
    """Retorna a base de dados (criada on-demand)."""
    global _db
    if _db is None:
        _db = get_motor_client()[db_name]
    return _db


def get_db():
    """Alias para get_database() - compatibilidade com testes."""
    return get_database()


class DatabaseProxy:
    """
    Proxy para acesso à DB que cria a conexão on-demand.
    Permite usar `db.collection.find()` como antes.
    """
    def __getattr__(self, name):
        return getattr(get_database(), name)


class ClientProxy:
    """
    Proxy para o cliente Motor que permite acesso lazy.
    """
    def close(self):
        reset_db_connection()
    
    def __getattr__(self, name):
        return getattr(get_motor_client(), name)


# Manter compatibilidade com código existente: `from database import db, client`
db = DatabaseProxy()
client = ClientProxy()
