# PowerCell - Sistema de Gestão de Processos

## Descrição

Sistema CRM para gestão de processos de crédito, clientes e documentação.

## Tecnologias

- **Backend**: FastAPI (Python)
- **Frontend**: React + Vite + TailwindCSS
- **Base de dados**: MongoDB
- **Armazenamento**: AWS S3
- **Deploy**: Render (backend) + Vercel (frontend)

## Estrutura do Projeto

```
PowerCell/
├── backend/
│   ├── routes/           # Endpoints da API
│   ├── services/         # Lógica de negócio
│   ├── models/           # Modelos de dados
│   ├── middleware/       # Middlewares (rate limiting, auth)
│   └── tests/            # Testes automatizados
├── frontend/
│   ├── src/
│   │   ├── components/   # Componentes React
│   │   ├── pages/        # Páginas da aplicação
│   │   ├── contexts/     # Contextos React
│   │   └── services/     # Serviços de API
│   └── public/
└── skills/               # Funcionalidades especializadas
```

## Funcionalidades Principais

- Gestão de Processos de Crédito
- Gestão de Clientes e Leads
- Upload e Gestão de Documentação (S3)
- Assinatura Digital de RGPD
- Links Temporários para Upload/Download
- Sistema de Notificações
- Dashboard e Estatísticas
- Integração com Email

## Configuração

### Variáveis de Ambiente

Backend:
- `MONGO_URL` - URL de conexão MongoDB
- `DB_NAME` - Nome da base de dados
- `JWT_SECRET` - Chave secreta para JWT
- `CORS_ORIGINS` - Origens permitidas (separadas por vírgula)
- `SENTRY_DSN` - DSN do Sentry (opcional)

Frontend:
- `REACT_APP_BACKEND_URL` - URL do backend

## Deploy

- **Backend**: Render (Docker)
- **Frontend**: Vercel

## Branches

- `main` - Produção
- `dev` - Desenvolvimento

## Licença

Privado - Power Real Estate
