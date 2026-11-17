"use client"
// NIM Studio — geração de imagens (FLUX.2-klein-4B), galeria e compreensão
// de imagem/vídeo (Nemotron omni). Usa /ai/nim/* com as credenciais da BD.
import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch, apiDownload, getUserRole } from '@/lib/api'
import { useLang } from '@/lib/i18n'
import { ImageIcon, Wand2, Eye, Loader2, Download, RefreshCw, Film, Play, Search, Trash2, FolderOpen, Images } from 'lucide-react'

type GalleryItem = {
  id: number, prompt: string, width: number, height: number, steps: number,
  seed: number | null, model: string, created_by: string, created_at: string,
  file_url: string,
}
type ImageRes = {
  id: number, image: string, width: number, height: number, steps: number,
  seed: number | null, model: string, latency_ms: number, source: string,
  file_url: string,
}
type VisionRes = { answer: string, model: string, media_type: string, latency_ms: number, source: string }
type BankProvider = { id: string, label: string, needs_key: boolean, configured: boolean, masked: string }
type BankResult = {
  provider: string, image_id: string, title: string, author: string,
  license: string, license_url: string, landing_url: string, url: string,
  thumb_url: string, width: number | null, height: number | null,
}
type BankSaved = {
  id: number, provider: string, provider_image_id: string, title: string,
  author: string, license: string, license_url: string, landing_url: string,
  width: number | null, height: number | null, created_at: string,
  thumb_url: string, file_url: string,
}

// fetch autenticado do JPEG da galeria → objectURL (img não envia Bearer)
function useThumb(fileUrl: string | null) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!fileUrl) { setUrl(null); return }
    let alive = true
    let objectUrl: string | null = null
    apiFetch(fileUrl)
      .then(r => r.ok ? r.blob() : Promise.reject(r.status))
      .then(b => {
        if (!alive) return
        objectUrl = URL.createObjectURL(b)
        setUrl(objectUrl)
      })
      .catch(() => { if (alive) setUrl(null) })
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [fileUrl])
  return url
}

function GalleryTile({ item, onDownload }: { item: GalleryItem, onDownload: (it: GalleryItem) => void }) {
  const { t } = useLang()
  const thumb = useThumb(item.file_url)
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800/50 group relative">
      {thumb ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={thumb} alt={item.prompt.slice(0, 60)} className="w-full aspect-square object-cover" />
      ) : (
        <div className="w-full aspect-square flex items-center justify-center text-slate-300 dark:text-slate-600">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      )}
      <button onClick={() => onDownload(item)}
        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-white/90 dark:bg-slate-900/90 rounded-lg p-1.5 shadow"
        title={t('nim.download')}>
        <Download className="w-3.5 h-3.5 text-slate-600 dark:text-slate-300" />
      </button>
      <div className="p-2">
        <p className="text-[11px] text-slate-600 dark:text-slate-300 line-clamp-2">{item.prompt}</p>
        <p className="text-[10px] text-slate-400 mt-0.5">{item.width}×{item.height} · {item.steps} steps · {item.created_at}</p>
      </div>
    </div>
  )
}

// Tile de resultado da busca (thumb por hotspot externo — sem auth)
function BankResultTile({ item, onSave, saving, savedIds }: { item: BankResult, onSave: (it: BankResult) => void, saving: boolean, savedIds: Set<string> }) {
  const { t } = useLang()
  const [broken, setBroken] = useState(false)
  const isSaved = savedIds.has(`${item.provider}:${item.image_id}`)
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800/50 group relative">
      {!broken && item.thumb_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={item.thumb_url} alt={item.title.slice(0, 60)} referrerPolicy="no-referrer" loading="lazy" onError={() => setBroken(true)}
          className="w-full aspect-square object-cover" />
      ) : (
        <div className="w-full aspect-square flex items-center justify-center text-slate-300 dark:text-slate-600">
          <ImageIcon className="w-5 h-5" />
        </div>
      )}
      <button onClick={() => onSave(item)} disabled={saving || isSaved}
        className="absolute top-2 right-2 bg-white/90 dark:bg-slate-900/90 rounded-lg p-1.5 shadow"
        title={isSaved ? t('bank.saved_title') : t('bank.save')}>
        {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
          : isSaved ? <FolderOpen className="w-3.5 h-3.5 text-emerald-600" />
          : <Download className="w-3.5 h-3.5 text-slate-600 dark:text-slate-300" />}
      </button>
      <div className="p-2">
        <p className="text-[11px] text-slate-600 dark:text-slate-300 line-clamp-2">{item.title || item.image_id}</p>
        <p className="text-[10px] text-slate-400 mt-0.5 truncate">{item.author || '—'}{item.license ? ` · ${item.license}` : ''}</p>
        {item.landing_url && (
          <a href={item.landing_url} target="_blank" rel="noreferrer"
            className="text-[10px] text-blue-500 hover:underline">{t('bank.license')} ↗</a>
        )}
      </div>
    </div>
  )
}

// Tile da galeria guardada (thumb servido pela API, com auth)
function BankSavedTile({ item, onDelete, deleting }: { item: BankSaved, onDelete?: (it: BankSaved) => void, deleting: boolean }) {
  const { t } = useLang()
  const thumb = useThumb(item.thumb_url)
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800/50 group relative">
      {thumb ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={thumb} alt={item.title.slice(0, 60)} className="w-full aspect-square object-cover" />
      ) : (
        <div className="w-full aspect-square flex items-center justify-center text-slate-300 dark:text-slate-600">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      )}
      <div className="absolute top-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={() => apiDownload(item.file_url, `bank_${item.id}.jpg`).catch(() => {})}
          className="bg-white/90 dark:bg-slate-900/90 rounded-lg p-1.5 shadow" title={t('nim.download')}>
          <Download className="w-3.5 h-3.5 text-slate-600 dark:text-slate-300" />
        </button>
        {onDelete && (
          <button onClick={() => onDelete(item)} disabled={deleting}
            className="bg-white/90 dark:bg-slate-900/90 rounded-lg p-1.5 shadow" title={t('bank.delete')}>
            {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin text-red-500" /> : <Trash2 className="w-3.5 h-3.5 text-red-500" />}
          </button>
        )}
      </div>
      <div className="p-2">
        <p className="text-[11px] text-slate-600 dark:text-slate-300 line-clamp-2">{item.title || item.provider}</p>
        <p className="text-[10px] text-slate-400 mt-0.5">{item.provider} · {item.license || '—'} · {item.created_at}</p>
      </div>
    </div>
  )
}

export function NimStudioCard() {
  const { t } = useLang()
  // --- geração de imagens ---
  const [prompt, setPrompt] = useState('')
  const [width, setWidth] = useState(1024)
  const [height, setHeight] = useState(1024)
  const [steps, setSteps] = useState(4)
  const [seed, setSeed] = useState('')
  const [genBusy, setGenBusy] = useState(false)
  const [result, setResult] = useState<ImageRes | null>(null)
  const [error, setError] = useState('')
  // --- galeria ---
  const [gallery, setGallery] = useState<GalleryItem[]>([])
  const [galBusy, setGalBusy] = useState(false)
  // --- visão ---
  const [vUrl, setVUrl] = useState('')
  const [vQuestion, setVQuestion] = useState('')
  const [vBusy, setVBusy] = useState(false)
  const [vRes, setVRes] = useState<VisionRes | null>(null)
  const [vError, setVError] = useState('')
  // --- banco de imagens ---
  const [bankProviders, setBankProviders] = useState<BankProvider[]>([])
  const [bankProvider, setBankProvider] = useState('met')
  const [bankQuery, setBankQuery] = useState('')
  const [bankResults, setBankResults] = useState<BankResult[]>([])
  const [bankCount, setBankCount] = useState<number | null>(null)
  const [bankBusy, setBankBusy] = useState(false)
  const [bankError, setBankError] = useState('')
  const [bankSearchDone, setBankSearchDone] = useState(false)
  const [bankSaved, setBankSaved] = useState<BankSaved[]>([])
  const [bankSaveBusyId, setBankSaveBusyId] = useState('')
  const [bankDeleteBusyId, setBankDeleteBusyId] = useState('')
  const canEditBank = getUserRole() === 'auditor' || getUserRole() === 'admin'
  const resultRef = useRef<HTMLDivElement | null>(null)

  const loadGallery = useCallback(async () => {
    setGalBusy(true)
    try {
      const r = await apiFetch('/ai/nim/images?limit=8')
      if (r.ok) {
        const d = await r.json()
        setGallery(d.images || [])
      }
    } catch { /* informativo */ }
    finally { setGalBusy(false) }
  }, [])
  useEffect(() => { loadGallery() /* eslint-disable-line react-hooks/exhaustive-deps */ }, [loadGallery])

  const loadBankProviders = useCallback(async () => {
    try {
      const r = await apiFetch('/ai/bank/providers')
      if (r.ok) {
        const d = await r.json()
        setBankProviders(d.providers || [])
      }
    } catch { /* informativo */ }
  }, [])
  const loadBankSaved = useCallback(async () => {
    try {
      const r = await apiFetch('/ai/bank/images?limit=8')
      if (r.ok) {
        const d = await r.json()
        setBankSaved(d.images || [])
      }
    } catch { /* informativo */ }
  }, [])
  useEffect(() => { loadBankProviders() /* eslint-disable-line react-hooks/exhaustive-deps */ }, [loadBankProviders])
  useEffect(() => { loadBankSaved() /* eslint-disable-line react-hooks/exhaustive-deps */ }, [loadBankSaved])

  async function bankSearch() {
    setBankError('')
    if (!bankQuery.trim()) { setBankError(`${t('bank.err')} ${t('bank.query')}`); return }
    setBankBusy(true); setBankResults([]); setBankSearchDone(false)
    try {
      const r = await apiFetch(`/ai/bank/search?q=${encodeURIComponent(bankQuery.trim())}&provider=${encodeURIComponent(bankProvider)}`)
      const d = await r.json()
      if (!r.ok) setBankError(d?.error || `${t('bank.err')} ${r.status}`)
      else { setBankResults(d.results || []); setBankCount(d.result_count ?? null); setBankSearchDone(true) }
    } catch { setBankError(t('bank.err')) }
    finally { setBankBusy(false) }
  }

  async function bankSave(item: BankResult) {
    setBankError(''); setBankSaveBusyId(`${item.provider}:${item.image_id}`)
    try {
      const r = await apiFetch('/ai/bank/save', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: item.provider, image_id: item.image_id,
          title: item.title, author: item.author, license: item.license,
          license_url: item.license_url, landing_url: item.landing_url,
          source_url: item.url, thumb_url: item.thumb_url,
          width: item.width, height: item.height,
          query: bankQuery.trim().slice(0, 300),
        })
      })
      const d = await r.json()
      if (!r.ok) setBankError(d?.error || `${t('bank.err')} ${r.status}`)
      else loadBankSaved()
    } catch { setBankError(t('bank.err')) }
    finally { setBankSaveBusyId('') }
  }

  async function bankDelete(item: BankSaved) {
    if (!window.confirm(`${t('bank.delete')}?`)) return
    setBankDeleteBusyId(String(item.id))
    try {
      const r = await apiFetch(`/ai/bank/images/${item.id}`, { method: 'DELETE' })
      if (r.ok) setBankSaved(xs => xs.filter(x => x.id !== item.id))
    } catch { /* silencioso */ }
    finally { setBankDeleteBusyId('') }
  }

  const bankSavedIds = new Set(bankSaved.map(s => `${s.provider}:${s.provider_image_id}`))

  async function generate() {
    setError('')
    if (!prompt.trim()) { setError(t('nim.prompt_required')); return }
    setGenBusy(true); setResult(null)
    try {
      const body: Record<string, unknown> = { prompt: prompt.trim(), width, height, steps }
      if (seed.trim() !== '' && !Number.isNaN(Number(seed))) body.seed = Number(seed)
      const r = await apiFetch('/ai/nim/image', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      const d = await r.json()
      if (!r.ok) setError(d?.error || `${t('nim.err')} ${r.status}`)
      else { setResult(d as ImageRes); loadGallery(); setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50) }
    } catch { setError(t('nim.err')) }
    finally { setGenBusy(false) }
  }

  async function analyse() {
    setVError(''); setVRes(null)
    if (!vUrl.trim()) { setVError(t('nim.prompt_required')); return }
    setVBusy(true)
    try {
      const r = await apiFetch('/ai/nim/vision', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: vUrl.trim(), question: vQuestion.trim() })
      })
      const d = await r.json()
      if (!r.ok) setVError(d?.error || `${t('nim.err')} ${r.status}`)
      else setVRes(d as VisionRes)
    } catch { setVError(t('nim.err')) }
    finally { setVBusy(false) }
  }

  function downloadResult(res: ImageRes) {
    const a = document.createElement('a')
    a.href = res.image
    a.download = `nim_${res.id}_${res.width}x${res.height}.jpg`
    document.body.appendChild(a); a.click(); a.remove()
  }
  function downloadGallery(it: GalleryItem) {
    apiDownload(it.file_url, `nim_${it.id}_${it.width}x${it.height}.jpg`).catch(() => {})
  }

  const isVideo = /\.(mp4|webm|mov|mkv|avi)(\?|$)/i.test(vUrl.trim())

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <ImageIcon className="w-4 h-4 text-fuchsia-600" />
        <p className="text-sm font-semibold text-gray-800 dark:text-slate-100">{t('nim.title')}</p>
        <span className="text-[11px] text-slate-400">{t('nim.subtitle')}</span>
      </div>

      {/* Geração de imagens */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2.5">
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">{t('nim.prompt')}</label>
          <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={3} maxLength={2000}
            placeholder={t('nim.prompt_ph')}
            className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-fuchsia-500 outline-none resize-y" />
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">{t('nim.size')}</label>
              <select value={`${width}x${height}`} onChange={e => { const [w, h] = e.target.value.split('x').map(Number); setWidth(w); setHeight(h) }}
                className="w-full px-2 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200">
                <option value="1024x1024">1024×1024</option>
                <option value="1024x768">1024×768</option>
                <option value="768x1024">768×1024</option>
                <option value="768x768">768×768</option>
                <option value="512x512">512×512</option>
              </select>
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">{t('nim.steps')}</label>
              <select value={steps} onChange={e => setSteps(Number(e.target.value))}
                className="w-full px-2 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200">
                {[2, 4, 6, 8].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">{t('nim.seed')}</label>
              <input value={seed} onChange={e => setSeed(e.target.value)} inputMode="numeric"
                className="w-full px-2 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={generate} disabled={genBusy}
              className="px-4 py-2 rounded-lg text-xs font-semibold bg-fuchsia-600 hover:bg-fuchsia-700 text-white flex items-center gap-1.5 disabled:opacity-50 transition-colors">
              {genBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
              {genBusy ? t('nim.generating') : t('nim.generate')}
            </button>
            {error && <span className="text-xs text-red-500">{error}</span>}
          </div>
        </div>
        <div ref={resultRef} className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 min-h-[220px] flex items-center justify-center overflow-hidden">
          {genBusy ? (
            <div className="flex flex-col items-center gap-2 text-slate-400 py-10">
              <Loader2 className="w-6 h-6 animate-spin" />
              <span className="text-xs">{t('nim.generating')}</span>
            </div>
          ) : result ? (
            <div className="w-full">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={result.image} alt={prompt.slice(0, 80)} className="w-full object-contain max-h-[420px]" />
              <div className="flex items-center justify-between gap-2 px-3 py-2">
                <span className="text-[10px] text-slate-400">
                  {result.width}×{result.height} · {t('nim.result_latency')} {result.latency_ms}ms · {result.source === 'db' ? t('nim.src_db') : result.source === 'env' ? t('nim.src_env') : result.source}
                </span>
                <button onClick={() => downloadResult(result)}
                  className="px-2.5 py-1 rounded-lg text-[11px] font-medium border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-1 transition-colors">
                  <Download className="w-3 h-3" /> {t('nim.download')}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 text-slate-300 dark:text-slate-600 py-10">
              <Wand2 className="w-6 h-6" />
              <span className="text-xs">FLUX.2-klein-4B</span>
            </div>
          )}
        </div>
      </div>

      {/* Galeria */}
      <div className="pt-1">
        <div className="flex items-center justify-between gap-2 mb-2">
          <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">{t('nim.gallery')}</p>
          <button onClick={loadGallery} disabled={galBusy}
            className="px-2.5 py-1 rounded-lg text-[11px] font-medium border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-1 disabled:opacity-50 transition-colors">
            {galBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} {t('ai.refresh')}
          </button>
        </div>
        {gallery.length === 0 ? (
          <p className="text-xs text-slate-400">{t('nim.gallery_empty')}</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            {gallery.map(it => <GalleryTile key={it.id} item={it} onDownload={downloadGallery} />)}
          </div>
        )}
      </div>

      {/* Banco de Imagens — busca real estilo Freepik */}
      <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <Images className="w-4 h-4 text-violet-600" />
          <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">{t('bank.title')}</p>
          <span className="text-[11px] text-slate-400">{t('bank.subtitle')}</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-[2fr_1.2fr_auto] gap-2">
          <input value={bankQuery} onChange={e => setBankQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') bankSearch() }}
            placeholder={t('bank.query_ph')}
            className="px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-violet-500 outline-none" />
          <select value={bankProvider} onChange={e => setBankProvider(e.target.value)}
            className="px-2 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200">
            {(bankProviders.length ? bankProviders : [{ id: 'openverse', label: 'Openverse (CC, sem chave)', needs_key: false, configured: true, masked: '' }]).map(p => (
              <option key={p.id} value={p.id} disabled={!p.configured}>
                {p.label}{p.needs_key && !p.configured ? ` — ${t('bank.need_key')}` : ''}
              </option>
            ))}
          </select>
          <button onClick={bankSearch} disabled={bankBusy}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-violet-600 hover:bg-violet-700 text-white flex items-center justify-center gap-1.5 disabled:opacity-50 transition-colors">
            {bankBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            {bankBusy ? t('bank.searching') : t('bank.search')}
          </button>
        </div>
        {bankError && <p className="text-xs text-red-500 mt-2">{bankError}</p>}
        {bankSearchDone && (
          <div className="mt-3">
            <p className="text-[11px] text-slate-400 mb-1.5">{t('bank.results')}{bankCount !== null ? ` · ${bankCount}` : ''}</p>
            {bankResults.length === 0 ? (
              <p className="text-xs text-slate-400">{t('bank.results_empty')}</p>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                {bankResults.map(r => (
                  <BankResultTile key={`${r.provider}:${r.image_id}`} item={r}
                    onSave={bankSave}
                    saving={bankSaveBusyId === `${r.provider}:${r.image_id}`}
                    savedIds={bankSavedIds} />
                ))}
              </div>
            )}
          </div>
        )}
        <div className="mt-3">
          <p className="text-[11px] text-slate-400 mb-1.5">{t('bank.saved_title')}</p>
          {bankSaved.length === 0 ? (
            <p className="text-xs text-slate-400">{t('bank.saved_empty')}</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
              {bankSaved.map(s => (
                <BankSavedTile key={s.id} item={s}
                  onDelete={canEditBank ? bankDelete : undefined}
                  deleting={bankDeleteBusyId === String(s.id)} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Visão (imagem/vídeo) */}
      <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-2 mb-2">
          {isVideo ? <Film className="w-4 h-4 text-cyan-600" /> : <Eye className="w-4 h-4 text-cyan-600" />}
          <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">{t('nim.vision_title')}</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-[2fr_1.5fr_auto] gap-2">
          <input value={vUrl} onChange={e => setVUrl(e.target.value)} placeholder={t('nim.vision_url')}
            className="px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-cyan-500 outline-none" />
          <input value={vQuestion} onChange={e => setVQuestion(e.target.value)} placeholder={t('nim.vision_q_ph')}
            className="px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-cyan-500 outline-none" />
          <button onClick={analyse} disabled={vBusy}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-700 text-white flex items-center justify-center gap-1.5 disabled:opacity-50 transition-colors">
            {vBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isVideo ? <Play className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            {vBusy ? t('nim.vision_analysing') : t('nim.vision_btn')}
          </button>
        </div>
        {vError && <p className="text-xs text-red-500 mt-2">{vError}</p>}
        {vRes && (
          <div className="mt-2.5 rounded-lg border border-cyan-100 dark:border-cyan-900/50 bg-cyan-50/60 dark:bg-cyan-900/20 p-3">
            <p className="text-sm text-slate-700 dark:text-slate-200">{vRes.answer}</p>
            <p className="text-[10px] text-slate-400 mt-1">
              {vRes.model} · {vRes.media_type} · {t('nim.result_latency')} {vRes.latency_ms}ms · {vRes.source === 'db' ? t('nim.src_db') : vRes.source === 'env' ? t('nim.src_env') : vRes.source}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
