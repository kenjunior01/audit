"use client"
import { useEffect, useState, useRef, useCallback } from 'react'
import { apiFetch } from '@/lib/api'
import { useRequireToken } from '@/lib/auth'
import { Search, RotateCcw, Info, X, MousePointer2, Move } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

type Node = {
  id: string
  type: 'user' | 'vendor' | 'transaction'
  label: string
  val: number
  risk: number
  x: number
  y: number
  vx: number
  vy: number
}

type Link = {
  source: string
  target: string
  risk?: number
  label?: string
  src?: Node
  tgt?: Node
}

export default function GraphPage() {
  const token = useRequireToken()
  const [data, setData] = useState<{nodes: Node[], links: Link[], collusion_risk?: any} | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [draggingNode, setDraggingNode] = useState<string | null>(null)
  
  // Ref to hold mutable node state for physics engine without triggering re-renders during calculation
  const simulationRef = useRef<{nodes: Node[], links: any[]}>({ nodes: [], links: [] })
  const requestRef = useRef<number>()
  
  const fetchGraph = (query?: string) => {
    setLoading(true)
    const url = query ? `/context/graph?pk=${query}` : '/context/graph'
    
    apiFetch(url)
      .then(res => {
          if (!res.ok) throw new Error('Failed to fetch')
          return res.json()
      })
      .then(d => {
        // Initialize positions randomly but centered
        const center = { x: 400, y: 300 }
        const nodesWithPos = (d.nodes || []).map((n: any) => ({
            ...n,
            x: center.x + (Math.random() - 0.5) * 200,
            y: center.y + (Math.random() - 0.5) * 200,
            vx: 0,
            vy: 0
        }))
        
        setData({ ...d, nodes: nodesWithPos })
        setLoading(false)
      })
      .catch(err => {
        console.error(err)
        setLoading(false)
        setData(null)
      })
  }

  useEffect(() => {
    if (token) {
      fetchGraph()
    }
  }, [token])

  // Physics Simulation Effect
  useEffect(() => {
    if (loading || !data) return

    let animationFrameId: number

    const tick = () => {
      setData(prev => {
        if (!prev || !prev.nodes) return prev

        // Clone nodes to avoid mutating state directly in render (though we are in setter)
        const nodes = prev.nodes.map(n => ({ ...n }))
        const links = prev.links

        // Constants
        const REPULSION = 500
        const SPRING_LENGTH = 120
        const SPRING_STRENGTH = 0.05
        const CENTER_GRAVITY = 0.02
        const MAX_VELOCITY = 15 // Increased for better movement

        // 1. Repulsion
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const n1 = nodes[i]
                const n2 = nodes[j]
                const dx = n1.x - n2.x
                const dy = n1.y - n2.y
                const dist = Math.sqrt(dx*dx + dy*dy) || 1
                if (dist < 500) {
                    const force = REPULSION / (dist * dist)
                    const fx = (dx / dist) * force
                    const fy = (dy / dist) * force
                    n1.vx += fx; n1.vy += fy;
                    n2.vx -= fx; n2.vy -= fy;
                }
            }
        }

        // 2. Spring
        links.forEach(link => {
            const source = nodes.find(n => n.id === link.source)
            const target = nodes.find(n => n.id === link.target)
            if (source && target) {
                const dx = target.x - source.x
                const dy = target.y - source.y
                const dist = Math.sqrt(dx*dx + dy*dy) || 1
                const force = (dist - SPRING_LENGTH) * SPRING_STRENGTH
                const fx = (dx / dist) * force
                const fy = (dy / dist) * force
                source.vx += fx; source.vy += fy;
                target.vx -= fx; target.vy -= fy;
            }
        })

        // 3. Gravity & Update
        const center = { x: 400, y: 300 }
        let maxV = 0
        nodes.forEach(n => {
             // Dragging override
             // Note: We can't easily access 'draggingNode' state here without adding it to dependency,
             // which restarts the loop. A ref for draggingNode is better.
             // For now, let's just let physics run. Dragging will fight physics or we ignore it here.
             
             n.vx += (center.x - n.x) * CENTER_GRAVITY
             n.vy += (center.y - n.y) * CENTER_GRAVITY
             n.vx *= 0.85
             n.vy *= 0.85
             
             const v = Math.sqrt(n.vx*n.vx + n.vy*n.vy)
             if (v > maxV) maxV = v
             
             n.x += n.vx
             n.y += n.vy
             
             // Bounds
             n.x = Math.max(20, Math.min(780, n.x))
             n.y = Math.max(20, Math.min(580, n.y))
        })
        
        // Stop simulation if stable (save CPU)
        if (maxV < 0.1) {
             // animationFrameId = requestAnimationFrame(tick) 
             // return { ...prev, nodes }
        }

        return { ...prev, nodes }
      })
      
      animationFrameId = requestAnimationFrame(tick)
    }

    // Start loop
    animationFrameId = requestAnimationFrame(tick)

    return () => cancelAnimationFrame(animationFrameId)
  }, [loading]) // Only run setup once when loading finishes (and data is ready)

  // Separate effect for Dragging to avoid restarting physics loop
  // We'll update the node position directly in the data state when dragging
  useEffect(() => {
      if (!draggingNode) return
      
      const handleMove = (e: MouseEvent) => {
           // We need to convert screen coords to SVG coords. 
           // Simplification: We assume the SVG is 800x600 and fits the screen or use offset.
           // This is tricky. Let's just skip "live drag" physics updates for now 
           // and just use the click to select.
      }
      // window.addEventListener('mousemove', handleMove)
      // return () => window.removeEventListener('mousemove', handleMove)
  }, [draggingNode])

  // Removed old runSimulation and effects


  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (searchQuery.trim()) {
      fetchGraph(searchQuery)
    }
  }

  const handleReset = () => {
    setSearchQuery('')
    fetchGraph()
  }

  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 })
  const [isPanning, setIsPanning] = useState(false)
  const [lastMouse, setLastMouse] = useState({ x: 0, y: 0 })

  // ... (existing effects)

  const handleWheel = (e: React.WheelEvent) => {
      e.stopPropagation()
      const zoomSensitivity = 0.001
      const newK = Math.min(Math.max(0.1, transform.k - e.deltaY * zoomSensitivity), 5)
      setTransform(prev => ({ ...prev, k: newK }))
  }

  const handleMouseDown = (e: React.MouseEvent, id?: string) => {
      e.stopPropagation()
      if (id) {
          setDraggingNode(id)
          draggingNodeRef.current = id
          // Initial mouse pos update
          if (svgRef.current) {
              const rect = svgRef.current.getBoundingClientRect()
              mousePosRef.current = {
                  x: (e.clientX - rect.left - transform.x) / transform.k,
                  y: (e.clientY - rect.top - transform.y) / transform.k
              }
          }
      } else {
          setIsPanning(true)
          setLastMouse({ x: e.clientX, y: e.clientY })
      }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
      if (draggingNodeRef.current) {
          if (svgRef.current) {
              const rect = svgRef.current.getBoundingClientRect()
              mousePosRef.current = {
                  x: (e.clientX - rect.left - transform.x) / transform.k,
                  y: (e.clientY - rect.top - transform.y) / transform.k
              }
          }
      } else if (isPanning) {
          const dx = e.clientX - lastMouse.x
          const dy = e.clientY - lastMouse.y
          setTransform(prev => ({ ...prev, x: prev.x + dx, y: prev.y + dy }))
          setLastMouse({ x: e.clientX, y: e.clientY })
      }
  }

  const handleMouseUp = () => {
      setDraggingNode(null)
      draggingNodeRef.current = null
      setIsPanning(false)
  }

  const renderGraph = () => {
    if (!data || !data.nodes || data.nodes.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-64 text-gray-500">
                <p>Nenhum dado encontrado para visualização.</p>
                <button onClick={handleReset} className="mt-4 text-indigo-600 hover:underline">Voltar ao Global</button>
            </div>
        )
    }

    return (
      <div 
        className="relative overflow-hidden h-[600px] w-full border rounded-xl shadow-inner bg-slate-50 dark:bg-slate-900/50 p-4 select-none cursor-move"
        onWheel={handleWheel}
        onMouseDown={(e) => handleMouseDown(e)}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
            <button className="p-2 bg-white rounded shadow hover:bg-gray-50" onClick={() => setTransform(p => ({...p, k: p.k * 1.2}))}>+</button>
            <button className="p-2 bg-white rounded shadow hover:bg-gray-50" onClick={() => setTransform(p => ({...p, k: p.k / 1.2}))}>-</button>
            <button className="p-2 bg-white rounded shadow hover:bg-gray-50" onClick={() => setTransform({x:0, y:0, k:1})}><RotateCcw className="w-4 h-4"/></button>
        </div>

        {data.collusion_risk && data.collusion_risk.detected && (
            <div className="absolute top-4 right-4 z-10 bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded shadow-lg max-w-sm animate-pulse pointer-events-none">
                <p className="font-bold flex items-center gap-2"><Info className="w-5 h-5"/> Risco de Colusão Detectado</p>
                <p className="text-sm mt-1">{data.collusion_risk.message}</p>
            </div>
        )}
        
        <svg ref={svgRef} width="100%" height="100%" viewBox="0 0 800 600" className="w-full h-full overflow-visible">
            <defs>
            <marker id="arrow" markerWidth="10" markerHeight="10" refX="24" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L9,3 z" fill="#94a3b8" />
            </marker>
            <marker id="arrow-red" markerWidth="10" markerHeight="10" refX="24" refY="3" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L9,3 z" fill="#ef4444" />
            </marker>
            </defs>
            
            <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.k})`}>
            {data.links.map((l, i) => {
                // Find node objects (since state updates might break references if we cloned deep)
                const src = data.nodes.find(n => n.id === l.source)
                const tgt = data.nodes.find(n => n.id === l.target)
                if (!src || !tgt) return null

                const isRisk = l.label === 'relacionamento suspeito' || (l.risk && l.risk > 0.7);
                return (
                <g key={i}>
                    <line 
                    x1={src.x} y1={src.y} 
                    x2={tgt.x} y2={tgt.y} 
                    stroke={isRisk ? '#ef4444' : '#cbd5e1'} 
                    strokeWidth={(isRisk ? 2 : 1.5) / transform.k} // Scale stroke width inversely
                    markerEnd={isRisk ? "url(#arrow-red)" : "url(#arrow)"}
                    opacity="0.6"
                    />
                </g>
            )})}

            {data.nodes.map((n) => (
            <g 
                key={n.id} 
                transform={`translate(${n.x},${n.y})`} 
                className="cursor-pointer hover:opacity-80 transition-opacity"
                onMouseDown={(e) => handleMouseDown(e, n.id)}
                onClick={(e) => { e.stopPropagation(); setSelectedNode(n); }}
            >
                <circle 
                r={(n.risk > 0.7 ? 24 : 18) / transform.k} // Scale radius inversely if desired, or keep fixed size
                fill={n.type === 'user' ? '#3b82f6' : n.type === 'vendor' ? '#10b981' : '#f59e0b'}
                stroke={n.risk > 0.7 ? '#ef4444' : 'white'}
                strokeWidth={(n.risk > 0.7 ? 3 : 2) / transform.k}
                className="shadow-sm transition-all"
                />
                <text y={5 / transform.k} textAnchor="middle" fill="white" fontSize={10 / transform.k} fontWeight="bold" pointerEvents="none">
                    {n.type === 'user' ? 'U' : n.type === 'vendor' ? 'V' : 'T'}
                </text>
                <text y={35 / transform.k} textAnchor="middle" fill="#475569" fontSize={11 / transform.k} fontWeight="600" className="pointer-events-none select-none">
                    {n.label}
                </text>
            </g>
            ))}
            </g>
        </svg>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto p-4">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                <Move className="w-6 h-6 text-indigo-500"/>
                Análise de Relacionamentos (Force Graph)
            </h1>
            <p className="text-gray-500 dark:text-gray-400">
                Visualize conexões dinâmicas. O layout se ajusta automaticamente.
            </p>
        </div>
        
        <form onSubmit={handleSearch} className="flex gap-2 w-full md:w-auto">
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input 
                    type="text" 
                    placeholder="ID da Transação..." 
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    className="pl-9 pr-4 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-indigo-500 outline-none w-full md:w-64"
                />
            </div>
            <button type="submit" className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
                Buscar
            </button>
            {searchQuery && (
                <button type="button" onClick={handleReset} className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
                    <RotateCcw className="w-5 h-5" />
                </button>
            )}
        </form>
      </div>

      <div className="flex justify-center">
        {loading ? (
            <div className="p-12 text-center text-gray-500 animate-pulse">
                <RotateCcw className="w-8 h-8 mx-auto mb-2 animate-spin text-indigo-400"/>
                Calculando layout de força...
            </div>
        ) : renderGraph()}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-xl border border-blue-100 dark:border-blue-800">
          <h3 className="font-bold text-blue-800 dark:text-blue-300 mb-1">Usuários (Aprovadores)</h3>
          <p className="text-xs text-blue-600 dark:text-blue-400">Nós azuis. Centralizam conexões.</p>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 p-4 rounded-xl border border-green-100 dark:border-green-800">
          <h3 className="font-bold text-green-800 dark:text-green-300 mb-1">Fornecedores</h3>
          <p className="text-xs text-green-600 dark:text-green-400">Nós verdes. Podem formar clusters.</p>
        </div>
        <div className="bg-yellow-50 dark:bg-yellow-900/20 p-4 rounded-xl border border-yellow-100 dark:border-yellow-800">
          <h3 className="font-bold text-yellow-800 dark:text-yellow-300 mb-1">Transações</h3>
          <p className="text-xs text-yellow-600 dark:text-yellow-400">Nós laranjas. Ligam usuários e fornecedores.</p>
        </div>
      </div>

      <AnimatePresence>
        {selectedNode && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={() => setSelectedNode(null)}>
                <motion.div 
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    onClick={e => e.stopPropagation()}
                    className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-md w-full p-6 border border-gray-200 dark:border-gray-700"
                >
                    <div className="flex justify-between items-start mb-4">
                        <div>
                            <span className={`text-xs font-bold px-2 py-1 rounded uppercase ${
                                selectedNode.type === 'user' ? 'bg-blue-100 text-blue-800' : 
                                selectedNode.type === 'vendor' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                            }`}>
                                {selectedNode.type}
                            </span>
                            <h2 className="text-xl font-bold mt-2 text-gray-900 dark:text-white">{selectedNode.label}</h2>
                        </div>
                        <button onClick={() => setSelectedNode(null)} className="text-gray-400 hover:text-gray-600">
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                    
                    <div className="space-y-4">
                        <div className="bg-gray-50 dark:bg-gray-900 p-3 rounded-lg">
                            <div className="text-sm text-gray-500">Nível de Risco</div>
                            <div className={`text-2xl font-bold ${selectedNode.risk > 0.7 ? 'text-red-600' : 'text-gray-800'}`}>
                                {(selectedNode.risk * 100).toFixed(1)}%
                            </div>
                        </div>
                        
                        <p className="text-sm text-gray-600 dark:text-gray-300">
                            ID: <span className="font-mono">{selectedNode.id}</span>
                        </p>

                        <div className="flex gap-2">
                            {selectedNode.type === 'transaction' && (
                                <>
                                    <button 
                                        onClick={() => window.location.href = `/transactions?search=${selectedNode.id}`}
                                        className="flex-1 py-2 bg-white border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-sm font-medium"
                                    >
                                        Ver Detalhes
                                    </button>
                                    <button 
                                        onClick={() => { fetchGraph(selectedNode.id); setSelectedNode(null); }}
                                        className="flex-1 py-2 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded-lg hover:bg-indigo-100 transition-colors text-sm font-medium"
                                    >
                                        Expandir
                                    </button>
                                </>
                            )}
                        </div>

                        <button 
                            onClick={() => setSelectedNode(null)}
                            className="w-full py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                        >
                            Fechar
                        </button>
                    </div>
                </motion.div>
            </div>
        )}
      </AnimatePresence>
    </div>
  )
}
