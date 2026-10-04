# Política de Segurança — AuditAI

## Reportar uma vulnerabilidade

Se encontrou uma vulnerabilidade (ex.: fuga de dados, injeção, escalonamento
de privilégios), **não abra uma issue pública**. Contacte o maintainer
diretamente com: descrição, passos para reproduzir, impacto e, se possível,
uma proposta de correção. Resposta esperada: 5 dias úteis.

## Modelo de ameaças e controlos implementados

| Área | Controlo |
|---|---|
| Autenticação | ApiToken por utilizador com papel (`admin`/`analyst`/`viewer`); tokens nunca gravados em claro no cliente |
| Autorização | `IsAuthenticated` por omissão em toda a API; ações agénticas com whitelist + validação de papel (v7) |
| Log imutável | `ImmutableAuditLog` para ações sensíveis (execuções do copiloto, exports) |
| Rate limiting | DRF throttling: `60/min` anónimo, `600/min` autenticado (`AUDIT_THROTTLE_*`) |
| Uploads | Limite de 25 MB; validação de tipo/estrutura no Excel Studio |
| Injeção | Todo o HTML dinâmico do digest/email é escapado (`html.escape`); queries via ORM |
| Headers | `X_FRAME_OPTIONS=DENY`, `SECURE_CONTENT_TYPE_NOSNIFF`, HSTS quando `AUDIT_DJANGO_SECRET_KEY` definida em prod |
| Cookies | `SECURE`/`CSRF` flags ativáveis com `AUDIT_SSL_REDIRECT=True` |
| CORS | Fechado por omissão em produção (`AUDIT_CORS_ALLOW_ALL=False`) |
| LLM self-hosted | Ollama/Qdrant nunca expõem dados a serviços externos; fallback determinístico sem rede |

## Checklist de produção

1. `AUDIT_DJANGO_SECRET_KEY` com valor aleatório longo (obrigatório — ativa HSTS).
2. `AUDIT_DEBUG=False` e `AUDIT_ALLOWED_HOSTS` explícito.
3. `AUDIT_SSL_REDIRECT=True` atrás de proxy HTTPS.
4. PostgreSQL via `AUDIT_DATABASE_URL` (não usar SQLite em produção).
5. SMTP real configurado (`AUDIT_EMAIL_BACKEND=…smtp.EmailBackend` + credenciais).
6. `AUDIT_CORS_ORIGINS` restrito às origens legítimas.
7. Rodar com gunicorn (ver `docker/entrypoint.backend.sh`) e worker celery
   separado (`docker-compose.yml`, perfil `worker`) para o digest programado.

## Gestão de credenciais do repositório

- **PATs do GitHub**: criar com escopo mínimo (`repo`), prazo curto e rodar
  periodicamente. Um PAT exposto em conversas, logs ou screenshots deve ser
  **revogado imediatamente** (GitHub → Settings → Developer settings →
  Personal access tokens) e substituído.
- Nunca commitar `.env`, tokens ou palavras-passe — usar `.env.example`
  apenas como template e o store de segredos da plataforma de deploy.
- O remote git local pode guardar o token em `.git/config` (URL remoto);
  preferir credential helper (`git config credential.helper store` ou
  `gh auth login`) e limpar o URL após uso:
  `git remote set-url origin https://github.com/OWNER/REPO.git`
