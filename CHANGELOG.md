# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

## [Não publicado]

## [2026-03-20] - Correções de Bugs

### Corrigido
- **RGPD Status Endpoint** (`/api/rgpd/status/{process_id}`)
  - Adicionada validação de UUID para `process_id`
  - Melhorado tratamento de erros para evitar erro 500
  - Adicionado `exc_info=True` para logs detalhados
  - Respostas de erro agora retornam `has_rgpd=False` em vez de crashar

- **Temp Links Create Endpoint** (`/api/temp-links/create`)
  - Adicionada validação de `process_id` vazio
  - Melhorado logging com informações de debug
  - Mensagens de erro mais descritivas
  - Tratamento de exceções mais robusto

- **RGPD Service** (`get_rgpd_by_process`)
  - Adicionada validação de entrada
  - Melhorado tratamento de erros de base de dados
  - Corrigido parsing de datas com diferentes formatos
  - Tratamento de erros `TypeError` adicional

### Documentação
- Criado README.md com documentação do projeto
- Criado CHANGELOG.md para registo de alterações

## Correções Anteriores

### RGPD e Temp Links
- Sistema de consentimentos RGPD com tokens temporários
- Links temporários para upload/download de documentação
- Notificações por email para clientes

### Segurança
- Rate limiting por utilizador
- Headers de segurança HTTP
- Validação de JWT
- CORS configurado com fail-secure

### Performance
- Índices de base de dados otimizados
- Paginação com cursor
- Cache de NIF para importações
