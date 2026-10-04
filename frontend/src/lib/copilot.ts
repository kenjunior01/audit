/**
 * Ponte global com o Copiloto Dock.
 * Qualquer página/componente pode pedir uma pergunta ao copiloto:
 *
 *   import { askCopilot } from '@/lib/copilot'
 *   askCopilot('Explica o alerta 42 e o que devo fazer')
 *
 * O dock (montado no layout) abre o painel e envia a pergunta com o
 * contexto da página atual — suporte contextual em toda a plataforma.
 */
export const COPILOT_ASK_EVENT = 'copilot:ask'

export function askCopilot(question: string): void {
  const q = (question || '').trim()
  if (!q || typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(COPILOT_ASK_EVENT, { detail: { question: q } }))
}
