# Plano de Ação: Auditoria Inteligente e Command Center

Este documento detalha o estado atual do sistema, as correções realizadas e um roteiro estratégico para implementação e inovação futura.

## 1. Diagnóstico e Correções Realizadas (Status Atual)

Identificamos e resolvemos diversos pontos críticos que impediam o funcionamento correto da plataforma.

### ✅ Páginas e Funcionalidades Recuperadas
*   **Alertas (Alerts Page):**
    *   **Problema:** Erro 500 devido a falha no serializador (campo `category` ausente no modelo Alert).
    *   **Correção:** Mapeamento correto do campo via `ReadOnlyField` apontando para `transaction.category`.
    *   **Melhoria:** Implementação de polling em tempo real para atualização automática de novos alertas.
*   **Análise de Grafo (Graph Analysis):**
    *   **Problema:** Layout estático e pouco funcional; falta de interatividade; endpoints retornando 403 (Proibido).
    *   **Correção:** Implementação de busca por ID de transação, melhoria visual do grafo (SVG dinâmico), modal de detalhes e correção de permissões no backend.
*   **Risco Geográfico (GeoRisk):**
    *   **Problema:** Página vazia por falta de dados e erro de autenticação.
    *   **Correção:** Script de "seeding" para popular dados geográficos fictícios e correção do fluxo de autenticação no frontend.
*   **Automação (Rule Builder):**
    *   **Problema:** Endpoint de sugestões inteligentes incorreto (`/suggest-rules` vs `/ai/suggest_rules`).
    *   **Correção:** Ajuste na rota da API e melhoria na aplicação das sugestões no formulário (mapeamento de ações).
*   **Gestão de Casos (Case Management):**
    *   **Problema:** Erros na criação de casos e comentários (Serializers bloqueando campos de leitura).
    *   **Correção:** Ajuste nos serializers (`ReadOnlyField` para `user_id`, `created_by`) e vinculação correta de transações aos casos.
*   **Configurações (Settings):**
    *   **Status:** Verificado e funcional.

### ✅ Infraestrutura e Testes
*   **Testes Automatizados:** Criação de suítes de teste (`test_critical_flows.py`, `test_workflow_pages.py`) cobrindo fluxos críticos (Alertas, Casos, Automação).
*   **Autenticação:** Correção nas classes de permissão (`IsViewerOrAbove`) herdando corretamente de `BasePermission`.

---

## 2. Plano de Implementação e Correção

Para garantir a estabilidade e o crescimento sustentável da plataforma, propomos o seguinte cronograma:

### Fase 1: Estabilização (Imediato - Concluído/Em andamento)
*   [x] Corrigir erros 500 e 403 em endpoints críticos.
*   [x] Validar fluxo de ponta a ponta (Transação -> Alerta -> Caso).
*   [x] Garantir que todas as páginas carreguem dados corretamente (com dados de demonstração se necessário).

### Fase 2: Otimização de UX (Curto Prazo - 1 semana)
*   **Dashboard Adaptativo:** Refinar o layout baseado na persona do usuário (já iniciado). Ex: Auditores veem mais detalhes técnicos, Gestores veem KPIs macro.
*   **Feedback Visual:** Adicionar "loading skeletons" e mensagens de erro mais amigáveis em todas as tabelas e gráficos.
*   **Filtros Avançados:** Implementar filtros por data, valor e fornecedor na página de Transações e Alertas.

### Fase 3: Segurança e Performance (Médio Prazo - 2-4 semanas)
*   **Rate Limiting:** Proteger a API contra abuso.
*   **Audit Logging:** Registrar todas as ações dos usuários (quem aprovou regra, quem fechou caso) para auditoria interna.
*   **Cache:** Implementar Redis para cachear resultados pesados (como o Grafo Global e GeoRisk).

---

## 3. Sugestões de Inovação (Value-Added Features)

Funcionalidades sugeridas para elevar o valor de negócio da plataforma:

### 🚀 1. Agentes de Auditoria Autônomos (AI Agents)
Em vez de apenas regras estáticas ("Se valor > 50k"), implementar agentes que investigam ativamente:
*   **Agente de Preços:** Compara preços de itens na nota fiscal com média de mercado em tempo real.
*   **Agente de Vínculos:** Busca na web (OSINT) por relações societárias entre funcionários e fornecedores não declaradas.

### 🔮 2. Análise Preditiva de Fraude (Forecasting)
*   Utilizar modelos de série temporal (Prophet/LSTM) para prever o volume de alertas futuros.
*   Antecipar picos de risco sazonal (ex: final de ano fiscal) e sugerir reforço na equipe de auditoria.

### 🔗 3. Auditoria Imutável (Blockchain)
*   Registrar o "hash" de cada auditoria e aprovação em uma blockchain privada ou ledger imutável.
*   Garante que evidências e decisões de auditoria não possam ser alteradas retroativamente (integridade total).

### 💬 4. Assistente de Auditoria Conversacional (ChatOps)
*   Expandir o "Audit Chat" para realizar ações via Slack/Teams.
*   Exemplo: O auditor recebe um alerta no Slack e responde "Investigar fornecedor X", e o bot cria o caso, anexa relatórios e retorna o resumo.

### 📊 5. Process Mining (Mineração de Processos)
*   Visualizar não apenas o grafo de conexões, mas o **fluxo do processo** de aprovação.
*   Identificar gargalos (onde os processos param) e desvios do fluxo padrão (quem pula etapas de aprovação).

---

Este plano serve como guia para as próximas sprints de desenvolvimento, focando primeiro na solidez da base atual e expandindo para funcionalidades de IA avançada.
