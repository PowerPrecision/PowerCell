#!/usr/bin/env python3
"""
Script de Migração de Base de Dados MongoDB

Este script permite:
1. Exportar todos os dados da base de dados atual para ficheiros JSON
2. Importar dados de ficheiros JSON para uma nova base de dados
3. Migrar directamente de uma BD para outra

Uso:
    # Exportar dados para ficheiros JSON
    python migrate_database.py export --output ./backup
    
    # Importar dados de ficheiros JSON
    python migrate_database.py import --input ./backup --target-url "mongodb+srv://..."
    
    # Migrar directamente de uma BD para outra
    python migrate_database.py migrate --target-url "mongodb+srv://..." --target-db "nova_db"
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Adicionar o diretório pai ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId, json_util
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder para tipos MongoDB"""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return {"$oid": str(obj)}
        if isinstance(obj, datetime):
            return {"$date": obj.isoformat()}
        return super().default(obj)


def json_serial(obj):
    """Serializer para JSON com suporte a tipos MongoDB"""
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


class DatabaseMigrator:
    """Classe para migração de base de dados MongoDB"""
    
    def __init__(self):
        self.source_url = os.getenv("MONGO_URL")
        self.source_db_name = os.getenv("DB_NAME", "powercell")
        
        if not self.source_url:
            raise ValueError("MONGO_URL não definido no ambiente")
    
    async def get_source_client(self):
        """Obter cliente MongoDB da fonte"""
        client = AsyncIOMotorClient(self.source_url)
        return client
    
    async def get_target_client(self, target_url: str):
        """Obter cliente MongoDB do destino"""
        client = AsyncIOMotorClient(target_url)
        return client
    
    async def list_collections(self, db) -> list:
        """Listar todas as collections da base de dados"""
        collections = await db.list_collection_names()
        # Filtrar collections de sistema
        return [c for c in collections if not c.startswith("system.")]
    
    async def export_to_json(self, output_dir: str):
        """
        Exportar todos os dados para ficheiros JSON
        
        Args:
            output_dir: Diretório de saída para os ficheiros JSON
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        print(f"\n{'='*60}")
        print(f"EXPORTAÇÃO DE BASE DE DADOS")
        print(f"{'='*60}")
        print(f"Fonte: {self.source_db_name}")
        print(f"Destino: {output_path.absolute()}")
        print(f"{'='*60}\n")
        
        client = await self.get_source_client()
        db = client[self.source_db_name]
        
        collections = await self.list_collections(db)
        print(f"Collections encontradas: {len(collections)}")
        print(f"Collections: {', '.join(collections)}\n")
        
        stats = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source_db": self.source_db_name,
            "collections": {}
        }
        
        for collection_name in collections:
            print(f"Exportando: {collection_name}...", end=" ")
            
            collection = db[collection_name]
            documents = await collection.find({}).to_list(None)
            
            # Converter ObjectId e datetime para strings
            serialized_docs = json.loads(json_util.dumps(documents))
            
            # Guardar em ficheiro
            file_path = output_path / f"{collection_name}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(serialized_docs, f, ensure_ascii=False, indent=2)
            
            count = len(documents)
            stats["collections"][collection_name] = count
            print(f"{count} documentos")
        
        # Guardar estatísticas
        stats_path = output_path / "_migration_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*60}")
        print(f"EXPORTAÇÃO CONCLUÍDA")
        print(f"{'='*60}")
        print(f"Total de collections: {len(collections)}")
        print(f"Total de documentos: {sum(stats['collections'].values())}")
        print(f"Ficheiros guardados em: {output_path.absolute()}")
        print(f"{'='*60}\n")
        
        client.close()
        return stats
    
    async def import_from_json(self, input_dir: str, target_url: str, target_db_name: str, 
                                drop_existing: bool = False):
        """
        Importar dados de ficheiros JSON para uma nova base de dados
        
        Args:
            input_dir: Diretório com os ficheiros JSON
            target_url: URL da base de dados de destino
            target_db_name: Nome da base de dados de destino
            drop_existing: Se True, elimina collections existentes antes de importar
        """
        input_path = Path(input_dir)
        
        if not input_path.exists():
            raise ValueError(f"Diretório não encontrado: {input_path}")
        
        print(f"\n{'='*60}")
        print(f"IMPORTAÇÃO DE BASE DE DADOS")
        print(f"{'='*60}")
        print(f"Fonte: {input_path.absolute()}")
        print(f"Destino: {target_db_name}")
        print(f"Drop existing: {drop_existing}")
        print(f"{'='*60}\n")
        
        # Listar ficheiros JSON
        json_files = list(input_path.glob("*.json"))
        json_files = [f for f in json_files if not f.name.startswith("_")]
        
        if not json_files:
            print("Nenhum ficheiro JSON encontrado!")
            return
        
        print(f"Ficheiros encontrados: {len(json_files)}")
        
        client = await self.get_target_client(target_url)
        db = client[target_db_name]
        
        stats = {
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "target_db": target_db_name,
            "collections": {}
        }
        
        for json_file in json_files:
            collection_name = json_file.stem
            print(f"Importando: {collection_name}...", end=" ")
            
            # Ler ficheiro
            with open(json_file, "r", encoding="utf-8") as f:
                documents = json.load(f)
            
            if not documents:
                print("vazio, ignorado")
                continue
            
            # Converter de volta para tipos MongoDB
            documents = json_util.loads(json.dumps(documents))
            
            collection = db[collection_name]
            
            # Eliminar collection existente se solicitado
            if drop_existing:
                await collection.drop()
            
            # Inserir documentos
            if isinstance(documents, list) and len(documents) > 0:
                await collection.insert_many(documents)
                count = len(documents)
            else:
                count = 0
            
            stats["collections"][collection_name] = count
            print(f"{count} documentos")
        
        print(f"\n{'='*60}")
        print(f"IMPORTAÇÃO CONCLUÍDA")
        print(f"{'='*60}")
        print(f"Total de collections: {len(stats['collections'])}")
        print(f"Total de documentos: {sum(stats['collections'].values())}")
        print(f"{'='*60}\n")
        
        client.close()
        return stats
    
    async def migrate_direct(self, target_url: str, target_db_name: str, 
                              drop_existing: bool = False,
                              collections_filter: Optional[list] = None):
        """
        Migrar directamente de uma base de dados para outra
        
        Args:
            target_url: URL da base de dados de destino
            target_db_name: Nome da base de dados de destino
            drop_existing: Se True, elimina collections existentes antes de migrar
            collections_filter: Lista de collections a migrar (None = todas)
        """
        print(f"\n{'='*60}")
        print(f"MIGRAÇÃO DIRECTA DE BASE DE DADOS")
        print(f"{'='*60}")
        print(f"Fonte: {self.source_db_name}")
        print(f"Destino: {target_db_name}")
        print(f"Drop existing: {drop_existing}")
        print(f"{'='*60}\n")
        
        source_client = await self.get_source_client()
        target_client = await self.get_target_client(target_url)
        
        source_db = source_client[self.source_db_name]
        target_db = target_client[target_db_name]
        
        collections = await self.list_collections(source_db)
        
        if collections_filter:
            collections = [c for c in collections if c in collections_filter]
        
        print(f"Collections a migrar: {len(collections)}")
        print(f"Collections: {', '.join(collections)}\n")
        
        stats = {
            "migrated_at": datetime.now(timezone.utc).isoformat(),
            "source_db": self.source_db_name,
            "target_db": target_db_name,
            "collections": {}
        }
        
        for collection_name in collections:
            print(f"Migrando: {collection_name}...", end=" ")
            
            source_collection = source_db[collection_name]
            target_collection = target_db[collection_name]
            
            # Eliminar collection existente se solicitado
            if drop_existing:
                await target_collection.drop()
            
            # Copiar documentos
            documents = await source_collection.find({}).to_list(None)
            
            if documents:
                # Remover _id para permitir inserção
                for doc in documents:
                    if "_id" in doc:
                        del doc["_id"]
                
                await target_collection.insert_many(documents)
                count = len(documents)
            else:
                count = 0
            
            stats["collections"][collection_name] = count
            print(f"{count} documentos")
        
        # Recriar índices
        print("\nRecriando índices...")
        for collection_name in collections:
            source_collection = source_db[collection_name]
            target_collection = target_db[collection_name]
            
            indexes = await source_collection.index_information()
            for index_name, index_info in indexes.items():
                if index_name == "_id_":
                    continue  # Ignorar índice _id (criado automaticamente)
                
                try:
                    keys = index_info.get("key", [])
                    if keys:
                        await target_collection.create_index(
                            keys,
                            name=index_name,
                            unique=index_info.get("unique", False),
                            sparse=index_info.get("sparse", False)
                        )
                        print(f"  Índice criado: {collection_name}.{index_name}")
                except Exception as e:
                    print(f"  Erro ao criar índice {index_name}: {e}")
        
        print(f"\n{'='*60}")
        print(f"MIGRAÇÃO CONCLUÍDA")
        print(f"{'='*60}")
        print(f"Total de collections: {len(stats['collections'])}")
        print(f"Total de documentos: {sum(stats['collections'].values())}")
        print(f"{'='*60}\n")
        
        source_client.close()
        target_client.close()
        return stats
    
    async def verify_migration(self, target_url: str, target_db_name: str):
        """
        Verificar se a migração foi bem sucedida comparando contagens
        
        Args:
            target_url: URL da base de dados de destino
            target_db_name: Nome da base de dados de destino
        """
        print(f"\n{'='*60}")
        print(f"VERIFICAÇÃO DE MIGRAÇÃO")
        print(f"{'='*60}\n")
        
        source_client = await self.get_source_client()
        target_client = await self.get_target_client(target_url)
        
        source_db = source_client[self.source_db_name]
        target_db = target_client[target_db_name]
        
        source_collections = await self.list_collections(source_db)
        target_collections = await self.list_collections(target_db)
        
        print(f"{'Collection':<30} {'Fonte':<15} {'Destino':<15} {'Status'}")
        print("-" * 75)
        
        all_ok = True
        for collection_name in source_collections:
            source_count = await source_db[collection_name].count_documents({})
            
            if collection_name in target_collections:
                target_count = await target_db[collection_name].count_documents({})
                status = "✅ OK" if source_count == target_count else "❌ DIFERENTE"
                if source_count != target_count:
                    all_ok = False
            else:
                target_count = 0
                status = "❌ NÃO EXISTE"
                all_ok = False
            
            print(f"{collection_name:<30} {source_count:<15} {target_count:<15} {status}")
        
        print("-" * 75)
        print(f"\nResultado: {'✅ Migração verificada com sucesso!' if all_ok else '❌ Existem diferenças!'}")
        
        source_client.close()
        target_client.close()
        
        return all_ok


def main():
    parser = argparse.ArgumentParser(
        description="Script de Migração de Base de Dados MongoDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:

  # Exportar dados para ficheiros JSON
  python migrate_database.py export --output ./backup
  
  # Importar dados de ficheiros JSON
  python migrate_database.py import --input ./backup --target-url "mongodb+srv://user:pass@cluster.mongodb.net" --target-db "nova_db"
  
  # Migrar directamente para outra BD
  python migrate_database.py migrate --target-url "mongodb+srv://user:pass@cluster.mongodb.net" --target-db "nova_db"
  
  # Verificar migração
  python migrate_database.py verify --target-url "mongodb+srv://user:pass@cluster.mongodb.net" --target-db "nova_db"
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Comando a executar")
    
    # Comando export
    export_parser = subparsers.add_parser("export", help="Exportar dados para ficheiros JSON")
    export_parser.add_argument("--output", "-o", default="./backup", help="Diretório de saída")
    
    # Comando import
    import_parser = subparsers.add_parser("import", help="Importar dados de ficheiros JSON")
    import_parser.add_argument("--input", "-i", required=True, help="Diretório com ficheiros JSON")
    import_parser.add_argument("--target-url", "-u", required=True, help="URL da BD de destino")
    import_parser.add_argument("--target-db", "-d", required=True, help="Nome da BD de destino")
    import_parser.add_argument("--drop", action="store_true", help="Eliminar collections existentes")
    
    # Comando migrate
    migrate_parser = subparsers.add_parser("migrate", help="Migrar directamente para outra BD")
    migrate_parser.add_argument("--target-url", "-u", required=True, help="URL da BD de destino")
    migrate_parser.add_argument("--target-db", "-d", required=True, help="Nome da BD de destino")
    migrate_parser.add_argument("--drop", action="store_true", help="Eliminar collections existentes")
    migrate_parser.add_argument("--collections", "-c", nargs="+", help="Collections específicas a migrar")
    
    # Comando verify
    verify_parser = subparsers.add_parser("verify", help="Verificar migração")
    verify_parser.add_argument("--target-url", "-u", required=True, help="URL da BD de destino")
    verify_parser.add_argument("--target-db", "-d", required=True, help="Nome da BD de destino")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    migrator = DatabaseMigrator()
    
    if args.command == "export":
        asyncio.run(migrator.export_to_json(args.output))
    
    elif args.command == "import":
        asyncio.run(migrator.import_from_json(
            args.input,
            args.target_url,
            args.target_db,
            drop_existing=args.drop
        ))
    
    elif args.command == "migrate":
        asyncio.run(migrator.migrate_direct(
            args.target_url,
            args.target_db,
            drop_existing=args.drop,
            collections_filter=args.collections
        ))
    
    elif args.command == "verify":
        asyncio.run(migrator.verify_migration(args.target_url, args.target_db))


if __name__ == "__main__":
    main()
