"use client"
// NIM Studio — geração de imagens (FLUX.2-klein-4B), galeria e compreensão
// de imagem/vídeo (Nemotron omni). Usa /ai/nim/* com as credenciais da BD.
import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch, apiDownload } from '@/lib/api'
import { useLang } from '@/lib/i18n'
import { ImageIcon, Wand2, Eye, Loader2, Download, RefreshCw, Film, Play } from 'lucide-react'

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
