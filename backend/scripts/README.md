# Scripts de Atribuição Automática de Clientes

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

# Não criar processos automaticamente
python scripts/auto_assign_clients.py --no-processes
```

**Opções:**
| Opção | Descrição |
|-------|-----------|
| `--dry-run` | Simula as atribuições sem guardar na base de dados |
| `--role` | Filtrar por role (consultor, mediador, indexacao) |
| `--limit` | Limite de clientes a processar (default: 100) |
| `--no-processes` | Não criar processos automaticamente |
| `--verbose, -v` | Mostrar mais detalhes |

---

### 2. `assign_specific_clients.py`

Atribui clientes específicos a utilizadores específicos.

**Uso:**
```bash
# Listar utilizadores disponíveis
python scripts/assign_specific_clients.py --list-users

# Listar clientes não atribuídos
python scripts/assign_specific_clients.py --list-unassigned

# Atribuir um cliente a um utilizador
python scripts/assign_specific_clients.py --client CLIENT_ID --user USER_ID

# Atribuir múltiplos clientes
python scripts/assign_specific_clients.py --clients ID1,ID2,ID3 --user USER_ID

# Não criar processo
python scripts/assign_specific_clients.py --client CLIENT_ID --user USER_ID --no-process
```

**Opções:**
| Opção | Descrição |
|-------|-----------|
| `--list-users` | Lista utilizadores disponíveis |
| `--list-unassigned` | Lista clientes não atribuídos |
| `--client` | ID do cliente a atribuir |
| `--clients` | IDs separados por vírgula |
| `--user` | ID do utilizador para atribuição |
| `--no-process` | Não criar processo automaticamente |
| `--limit` | Limite para listagem (default: 50) |

---

## Fluxo Recomendado

1. **Ver clientes não atribuídos:**
   ```bash
   python scripts/assign_specific_clients.py --list-unassigned
   ```

2. **Ver utilizadores disponíveis:**
   ```bash
   python scripts/assign_specific_clients.py --list-users
   ```

3. **Simular atribuição automática:**
   ```bash
   python scripts/auto_assign_clients.py --dry-run --verbose
   ```

4. **Executar atribuição real:**
   ```bash
   python scripts/auto_assign_clients.py
   ```

---

## Regras de Atribuição Automática

- Clientes são distribuídos de forma round-robin entre utilizadores
- Respeita capacidade máxima por role:
  - Consultor: 50 clientes
  - Mediador: 30 clientes
  - Indexação: 100 clientes
- Cria automaticamente um processo para cada cliente atribuído
- Prioriza utilizadores com mais capacidade disponível

---

## Execução em Produção

Para executar no servidor Render:

```bash
# Conectar via SSH ou usar shell do Render
cd /app/backend
python scripts/auto_assign_clients.py --dry-run
python scripts/auto_assign_clients.py
```

Ou configurar como tarefa agendada no sistema.
