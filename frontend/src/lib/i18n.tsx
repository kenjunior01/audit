"use client"
// i18n PT/EN — provider minimalista com persistência em localStorage.
// Dicionário plano de pares [pt, en] + hook useLang() + LangToggle.
// Padrão de uso: const { t, lang } = useLang(); t('studio.ask_title').
// Chave ausente devolve a própria chave (falha visível, nunca crash).
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Lang = 'pt' | 'en'

const DICT: Record<string, [string, string]> = {
  // --- shell: cabeçalho + sidebar ---
  'header.status': ['Estado do sistema:', 'System status:'],
  'nav.overview': ['Visão Geral', 'Overview'],
  'nav.studio': ['Painel Auto', 'Auto Panel'],
  'nav.inspect': ['Inspeção', 'Inspection'],
  'nav.risks': ['Riscos', 'Risks'],
  'nav.ai_gov': ['Governança AI', 'AI Governance'],
  'nav.cases': ['Casos', 'Cases'],
  'nav.sla': ['SLA', 'SLA'],
  'nav.assistant': ['Audit AI', 'Audit AI'],
  'nav.agents': ['Agentes', 'Agents'],
  'nav.excel': ['Excel Studio', 'Excel Studio'],
  'nav.bi': ['BI Studio', 'BI Studio'],
  'nav.connections': ['Conexões', 'Connections'],
  'nav.geo': ['Geo Risco', 'Geo Risk'],
  'nav.automation': ['Automação', 'Automation'],
  'nav.context': ['Contexto', 'Context'],
  'nav.integrations': ['Integrações', 'Integrations'],
  'nav.actions': ['Ações Externas', 'External Actions'],
  'nav.settings': ['Configuração', 'Settings'],
  'nav.settings_footer': ['Configurações', 'Settings'],
  'nav.logout': ['Sair', 'Sign out'],
  // --- Painel Auto (/studio) ---
  'studio.title': ['Painel Auto', 'Auto Panel'],
  'studio.subtitle': [
    'Um clique: o motor REA analisa os seus dados e monta o painel completo — KPIs, tendências, Pareto, anomalias e projeção.',
    'One click: the REA engine analyses your data and builds the full dashboard — KPIs, trends, Pareto, anomalies and forecast.'],
  'studio.in_breach': ['em violação', 'in breach'],
  'studio.generate': ['Gerar painel', 'Generate dashboard'],
  'studio.vol_xlsx': ['Volume (.xlsx)', 'Volume (.xlsx)'],
  'studio.series_xlsx': ['Série (.xlsx)', 'Series (.xlsx)'],
  'studio.advanced': ['Modo avançado', 'Advanced mode'],
  'period.all': ['Tudo', 'All'],
  'period.year': ['Este ano', 'This year'],
  'period.90': ['90 dias', '90 days'],
  'period.30': ['30 dias', '30 days'],
  'studio.records': ['transações', 'transactions'],
  'studio.ask_title': ['Pergunte aos dados', 'Ask your data'],
  'studio.ask_sub': ['em linguagem natural — resposta com gráfico', 'in natural language — answer with a chart'],
  'studio.ask_ph': ['ex.: gastos por fornecedor no último ano', 'e.g.: spend by supplier in the last year'],
  'studio.ask_btn': ['Perguntar', 'Ask'],
  'studio.conf': ['confiança', 'confidence'],
  'studio.loading': ['A analisar os seus dados…', 'Analysing your data…'],
  'studio.import_cta': ['Importar Excel agora', 'Import Excel now'],
  'studio.insights_title': ['O que os dados dizem', 'What the data says'],
  'studio.forecast': ['Projeção 3 meses', '3-month forecast'],
  'studio.anomalies': ['Anomalias mensais', 'Monthly anomalies'],
  'studio.evolution': ['Evolução mensal', 'Monthly evolution'],
  'studio.alerts_title': ['Alertas ao vivo', 'Live alerts'],
  'studio.alerts_sub': ['regras avaliadas automaticamente hora a hora', 'rules evaluated automatically every hour'],
  'studio.evaluate': ['Avaliar agora', 'Evaluate now'],
  'studio.evaluated': ['avaliado(s)', 'evaluated'],
  'studio.all_within': ['tudo dentro dos limiares', 'all within thresholds'],
  'studio.no_rules': ['Sem regras de monitorização ainda — crie sugestões com 1 clique na', 'No monitoring rules yet — create one-click suggestions in the'],
  'studio.excel_auto_link': ['Análise Auto do Excel Studio', 'Excel Studio Auto Analysis'],
  'studio.or_bi': ['ou no', 'or in the'],
  'studio.manage_alerts': ['Gerir alertas no BI Studio', 'Manage alerts in BI Studio'],
  'studio.current_value': ['valor atual:', 'current value:'],
  'studio.breaches': ['violação(ões)', 'breach(es)'],
  // --- estados de alerta + agregações ---
  'st.inactive': ['inativo', 'inactive'],
  'st.breach': ['em violação', 'in breach'],
  'st.error': ['erro', 'error'],
  'st.ok': ['OK', 'OK'],
  'st.none': ['sem avaliação', 'not evaluated'],
  'st.now': ['agora', 'now'],
  'st.min_ago': ['há', ''],
  'agg.count': ['contagem', 'count'],
  'agg.sum': ['soma', 'sum'],
  'agg.of': ['de', 'of'],
  'agg.measure': ['medida', 'measure'],
  // --- erros comuns ---
  'err.generate': ['falha ao gerar o painel', 'failed to generate the dashboard'],
  'err.export': ['falha na exportação', 'export failed'],
  'err.qa': ['sem ligação ao Q&A', 'Q&A unavailable'],
  'err.evaluate': ['falha ao avaliar os alertas', 'failed to evaluate alerts'],
  // --- motores de IA (LLM multi-provider) ---
  'ai.engines_title': ['Motores de IA', 'AI engines'],
  'ai.engines_sub': ['cadeia NVIDIA NIM → provider local', 'NVIDIA NIM → local provider chain'],
  'ai.refresh': ['Atualizar', 'Refresh'],
  'ai.test': ['Testar agora', 'Test now'],
  'ai.online': ['online', 'online'],
  'ai.none_available': [
    'Nenhum motor de IA disponível — configure AUDIT_NVIDIA_API_KEY ou um Ollama local.',
    'No AI engine available — set AUDIT_NVIDIA_API_KEY or a local Ollama.'],
  'ai.test_ok': ['Teste OK:', 'Test OK:'],
  'ai.test_fail': ['Teste falhou —', 'Test failed —'],
  'studio.ai_summary': ['Resumo IA', 'AI summary'],
  'studio.ai_thinking': ['A gerar interpretação IA…', 'Generating AI interpretation…'],
  'studio.ai_unavailable': ['IA indisponível — resumo determinístico.', 'AI unavailable — deterministic summary.'],
  'studio.ai_via': ['via', 'via'],
  // --- NIM Studio (imagens FLUX.2 + visão omni + credenciais BD) ---
  'nim.title': ['NIM Studio — Imagens & Visão', 'NIM Studio — Images & Vision'],
  'nim.subtitle': [
    'Gerar imagens (FLUX.2-klein-4B) e compreender imagem/vídeo (Nemotron omni) com as credenciais NVIDIA NIM da plataforma.',
    'Generate images (FLUX.2-klein-4B) and understand image/video (Nemotron omni) with the platform\'s NVIDIA NIM credentials.'],
  'nim.prompt': ['Prompt da imagem', 'Image prompt'],
  'nim.prompt_ph': ['ex.: dashboard de auditoria elegante, estilo corporativo, tons azuis', 'e.g.: elegant audit dashboard, corporate style, blue tones'],
  'nim.generate': ['Gerar imagem', 'Generate image'],
  'nim.generating': ['A gerar…', 'Generating…'],
  'nim.size': ['Tamanho', 'Size'],
  'nim.steps': ['Passos', 'Steps'],
  'nim.seed': ['Semente (opcional)', 'Seed (optional)'],
  'nim.download': ['Descarregar', 'Download'],
  'nim.result_latency': ['gerada em', 'generated in'],
  'nim.gallery': ['Galeria recente', 'Recent gallery'],
  'nim.gallery_empty': ['Sem imagens geradas ainda.', 'No images generated yet.'],
  'nim.vision_title': ['Compreensão de imagem/vídeo (omni)', 'Image/video understanding (omni)'],
  'nim.vision_url': ['URL da imagem ou vídeo', 'Image or video URL'],
  'nim.vision_q': ['Pergunta', 'Question'],
  'nim.vision_q_ph': ['ex.: O que há de suspeito nesta fatura?', 'e.g.: What is suspicious in this invoice?'],
  'nim.vision_btn': ['Analisar', 'Analyse'],
  'nim.vision_analysing': ['A analisar…', 'Analysing…'],
  'nim.err': ['Falha no NIM Studio —', 'NIM Studio failed —'],
  'nim.prompt_required': ['Escreve um prompt primeiro.', 'Write a prompt first.'],
  'nim.creds_title': ['Credenciais NVIDIA NIM (base de dados)', 'NVIDIA NIM credentials (database)'],
  'nim.creds_sub': [
    'Guardadas encriptadas (Fernet) na BD — geríveis sem reinício. Deixa vazio para manter a atual; vazio + guardar limpa (fallback: env).',
    'Stored encrypted (Fernet) in the DB — manageable without restart. Leave empty to keep current; empty + save clears (fallback: env).'],
  'nim.slot_text': ['Texto (Nemotron ultra)', 'Text (Nemotron ultra)'],
  'nim.slot_vision': ['Visão (omni 30B)', 'Vision (omni 30B)'],
  'nim.slot_image': ['Imagens (FLUX.2)', 'Images (FLUX.2)'],
  'nim.api_key': ['API key', 'API key'],
  'nim.model': ['Modelo', 'Model'],
  'nim.src_db': ['BD', 'DB'],
  'nim.src_env': ['Ambiente', 'Env'],
  'nim.src_none': ['não configurada', 'not configured'],
  'nim.creds_save': ['Guardar credenciais', 'Save credentials'],
  'nim.creds_saving': ['A guardar…', 'Saving…'],
  'nim.creds_ok': ['Credenciais atualizadas na BD.', 'Credentials saved to the DB.'],
  'nim.creds_forbidden': ['Só auditor/admin podem alterar credenciais.', 'Only auditor/admin can change credentials.'],
  'nim.model_default': ['omissão', 'default'],
}

type LangCtxT = { lang: Lang, setLang: (l: Lang) => void, t: (k: string) => string }

const LangCtx = createContext<LangCtxT>({
  lang: 'pt', setLang: () => {}, t: (k) => k,
})

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>('pt')
  useEffect(() => {
    try {
      const saved = localStorage.getItem('audit-lang')
      if (saved === 'en' || saved === 'pt') setLangState(saved)
    } catch { /* storage indisponível — mantém pt */ }
  }, [])
  const setLang = (l: Lang) => {
    setLangState(l)
    try { localStorage.setItem('audit-lang', l) } catch { /* noop */ }
  }
  const t = (k: string) => {
    const pair = DICT[k]
    if (!pair) return k
    return lang === 'en' ? pair[1] : pair[0]
  }
  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>
}

export const useLang = () => useContext(LangCtx)

export function LangToggle({ className = '' }: { className?: string }) {
  const { lang, setLang } = useLang()
  return (
    <div className={`flex items-center rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden text-[11px] font-semibold ${className}`}>
      {(['pt', 'en'] as Lang[]).map(l => (
        <button key={l} onClick={() => setLang(l)} aria-label={l === 'pt' ? 'Português' : 'English'}
          className={`px-2 py-1 transition-colors ${lang === l
            ? 'bg-blue-600 text-white'
            : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}`}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
