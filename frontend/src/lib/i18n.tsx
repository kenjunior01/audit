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
