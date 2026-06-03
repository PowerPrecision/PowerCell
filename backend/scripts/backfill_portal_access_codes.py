"""
Script de Backfill: Gerar códigos de acesso ao Portal para clientes existentes.

Este script deve ser executado uma vez após a migração para o sistema de
Código de Acesso Fixo. Ele gera códigos alfanuméricos (formato XXX-XXX)
para todos os clientes que ainda não possuem portal_access_code.

Uso:
    cd backend
    python -m scripts.backfill_portal_access_codes

Opcional: --dry-run para apenas mostrar quantos clientes precisam de código
          --send-emails para enviar email com o código a cada cliente
"""
import asyncio
import sys
import os

# Garantir que o backend/ está no path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from models.client import generate_portal_access_code


async def backfill_access_codes(dry_run: bool = False, send_emails: bool = False):
    """
    Gera portal_access_code para todos os clientes sem código.
    
    Args:
        dry_run: Se True, apenas conta quantos clientes precisam de código
        send_emails: Se True, envia email com o código a cada cliente
    """
    # Contar clientes sem código
    clients_without_code = await db.clients.find(
        {"$or": [
            {"portal_access_code": {"$exists": False}},
            {"portal_access_code": None},
            {"portal_access_code": ""},
        ]},
        {"_id": 0, "id": 1, "nome": 1, "contacto": 1, "portal_access_code": 1}
    ).to_list(100000)

    print(f"\n{'='*60}")
    print(f"BACKFILL: Códigos de Acesso ao Portal")
    print(f"{'='*60}")
    print(f"Clientes sem portal_access_code: {len(clients_without_code)}")

    if dry_run:
        print("\n[DRY RUN] Nenhuma alteração foi feita.")
        print(f"Execute sem --dry-run para gerar {len(clients_without_code)} códigos.")
        return

    if not clients_without_code:
        print("\nTodos os clientes já possuem código de acesso!")
        return

    updated = 0
    errors = 0

    for client in clients_without_code:
        client_id = client.get("id")
        client_name = client.get("nome", "Desconhecido")
        
        try:
            code = generate_portal_access_code()
            result = await db.clients.update_one(
                {"id": client_id},
                {"$set": {"portal_access_code": code}}
            )
            
            if result.modified_count > 0:
                updated += 1
                
                # Enviar email com o código (se solicitado)
                if send_emails:
                    contacto = client.get("contacto", {})
                    email = None
                    if isinstance(contacto, dict):
                        email = contacto.get("email")
                    
                    if email:
                        try:
                            from services.email import send_registration_confirmation
                            await send_registration_confirmation(
                                client_email=email,
                                client_name=client_name,
                                portal_access_code=code
                            )
                            print(f"  ✓ Email enviado para {email}")
                        except Exception as e:
                            print(f"  ✗ Erro ao enviar email para {email}: {e}")
                
                if updated % 50 == 0:
                    print(f"  Progresso: {updated}/{len(clients_without_code)}")
            else:
                errors += 1
                print(f"  ✗ Falha ao atualizar cliente {client_id}")
                
        except Exception as e:
            errors += 1
            print(f"  ✗ Erro no cliente {client_id} ({client_name}): {e}")

    print(f"\n{'='*60}")
    print(f"RESULTADO:")
    print(f"  Códigos gerados: {updated}")
    print(f"  Erros: {errors}")
    print(f"  Total processado: {len(clients_without_code)}")
    print(f"{'='*60}")


async def main():
    dry_run = "--dry-run" in sys.argv
    send_emails = "--send-emails" in sys.argv
    
    await backfill_access_codes(dry_run=dry_run, send_emails=send_emails)


if __name__ == "__main__":
    asyncio.run(main())
