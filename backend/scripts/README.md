# Scripts de Utilidade - PowerCell

## Scripts Disponíveis

### 1. `auto_assign_clients.py`

Atribui automaticamente clientes a utilizadores com distribuição round-robin.

**Uso:**
```bash
# Simular atribuições (sem guardar)
python scripts/auto_assign_clients.py --dry-run

# Executar atribuição real
python scripts/auto_assign_clients.py

# Filtrar por role de utilizador
python scripts/auto_assign_clients.py --role consultor

# Limitar número de clientes
python scripts/auto_assign_clients.py --limit 50

# Modo verbose
python scripts/auto_assign_clients.py --dry-run --verbose
```

**Opções:**
| Opção | Descrição |
|-------|-----------|
| `--dry-run` | Simula as atribuições sem guardar |
| `--role` | Filtrar por role (consultor, mediador, indexacao) |
| `--limit` | Limite de clientes a processar (default: 100) |
| `--no-processes` | Não criar processos automaticamente |
| `--verbose, -v` | Mostrar mais detalhes |

---

### 2. `cleanup_cliente_data.py`

Remove processos com `client_name: "Cliente"` (dados de teste).

**Uso:**
```bash
# Ver o que vai ser apagado (simulação)
python scripts/cleanup_cliente_data.py

# Executar limpeza
python scripts/cleanup_cliente_data.py --execute
```

---

### 3. `seed_test_clients.py`

Cria clientes e processos de teste com dados realistas portugueses.

**Uso:**
```bash
# Criar 100 clientes de teste
python scripts/seed_test_clients.py

# Criar 50 clientes
python scripts/seed_test_clients.py --count 50

# Limpar dados de teste existentes antes de criar
python scripts/seed_test_clients.py --clear
```

---

### 4. `migrate_database.py`

Migração de base de dados MongoDB (export/import/migrate).

**Uso:**
```bash
# Exportar dados para ficheiros JSON
python scripts/migrate_database.py export --output ./backup

# Importar dados de ficheiros JSON
python scripts/migrate_database.py import --input ./backup --target-url "mongodb+srv://..."

# Migrar diretamente de uma BD para outra
python scripts/migrate_database.py migrate --target-url "mongodb+srv://..." --target-db "nova_db"
```

---

## Regras de Atribuição Automática

- Clientes são distribuídos de forma round-robin entre utilizadores
- Respeita capacidade máxima por role:
  - Consultor: 50 clientes
  - Mediador/Intermediário: 30 clientes
  - Indexação: 100 clientes
  - CEO: 100 clientes
  - Diretor: 80 clientes
- Cria automaticamente um processo para cada cliente atribuído
- Prioriza utilizadores com mais capacidade disponível
