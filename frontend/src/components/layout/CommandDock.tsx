"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { motion, AnimatePresence } from "framer-motion"
import { 
  BarChart3,
  LayoutDashboard, 
  Search, 
  ShieldAlert, 
  Briefcase, 
  Bot, 
  Network, 
  Map, 
  Settings, 
  Upload, 
  Zap,
  Menu,
  ChevronRight,
  LogOut,
  Database,
  Clock,
  Users,
  ShieldCheck,
  Link2,
  Power,
  FileSpreadsheet,
  Sparkles
} from "lucide-react"
import { useLang } from "@/lib/i18n"

const menuItems = [
  { path: "/", k: "nav.overview", icon: LayoutDashboard },
  { path: "/studio", k: "nav.studio", icon: Sparkles },
  { path: "/transactions", k: "nav.inspect", icon: Search },
  { path: "/alerts", k: "nav.risks", icon: ShieldAlert },
  { path: "/governance", k: "nav.ai_gov", icon: ShieldCheck },
  { path: "/cases", k: "nav.cases", icon: Briefcase },
  { path: "/sla", k: "nav.sla", icon: Clock },
  { path: "/assistant", k: "nav.assistant", icon: Bot },
  { path: "/agents", k: "nav.agents", icon: Users },
  { path: "/excel", k: "nav.excel", icon: FileSpreadsheet },
  { path: "/bi", k: "nav.bi", icon: BarChart3 },
  { type: "divider" },
  { path: "/graph", k: "nav.connections", icon: Network },
  { path: "/geo-risk", k: "nav.geo", icon: Map },
  { path: "/automation", k: "nav.automation", icon: Zap },
  { path: "/context", k: "nav.context", icon: Database },
  { type: "divider" },
  { path: "/integrations", k: "nav.integrations", icon: Link2 },
  { path: "/external-actions", k: "nav.actions", icon: Power },
  { path: "/settings", k: "nav.settings", icon: Settings },
]

export function CommandDock() {
  const pathname = usePathname()
  const [isExpanded, setIsExpanded] = useState(false)
  const [isHovered, setIsHovered] = useState(false)
  const { t } = useLang()

  // Auto-collapse on route change
  useEffect(() => {
    setIsExpanded(false)
  }, [pathname])

  return (
    <motion.div
      className="fixed left-0 top-0 h-screen z-50 flex flex-col bg-slate-900/95 backdrop-blur-md border-r border-slate-800 text-slate-300 shadow-2xl"
      initial={{ width: "4rem" }}
      animate={{ width: isExpanded || isHovered ? "16rem" : "4.5rem" }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Header / Logo */}
      <div className="h-16 flex items-center px-4 border-b border-slate-800/50">
        <div className="flex items-center gap-3 overflow-hidden whitespace-nowrap">
          <div className="min-w-[2rem] h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-[0_0_15px_rgba(37,99,235,0.5)]">
            <ShieldAlert className="w-5 h-5 text-white" />
          </div>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: isExpanded || isHovered ? 1 : 0 }}
            transition={{ duration: 0.2 }}
            className="font-bold text-white tracking-wider"
          >
            AUDIT<span className="text-blue-500">CC</span>
          </motion.div>
        </div>
      </div>

      {/* Navigation Items */}
      <div className="flex-1 overflow-y-auto py-4 scrollbar-none">
        <nav className="flex flex-col gap-1 px-2">
          {menuItems.map((item, index) => {
            if (item.type === "divider") {
              return <div key={index} className="h-px bg-slate-800 my-2 mx-2" />
            }

            const isActive = pathname === item.path
            const Icon = item.icon!

            return (
              <Link key={item.path} href={item.path || "#"}>
                <div className="relative group flex items-center h-10 px-3 rounded-md cursor-pointer transition-all duration-200 hover:bg-slate-800/50">
                  {/* Active Indicator (Glow) */}
                  {isActive && (
                    <motion.div
                      layoutId="activeTab"
                      className="absolute inset-0 bg-blue-600/10 border border-blue-500/30 rounded-md shadow-[0_0_10px_rgba(37,99,235,0.2)]"
                      transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    />
                  )}
                  
                  {/* Active Indicator (Left Bar) */}
                  {isActive && (
                    <motion.div 
                      layoutId="activeBar"
                      className="absolute left-0 top-2 bottom-2 w-1 bg-blue-500 rounded-r-full" 
                    />
                  )}

                  <Icon className={`w-5 h-5 min-w-[1.25rem] z-10 transition-colors ${isActive ? "text-blue-400" : "text-slate-400 group-hover:text-white"}`} />
                  
                  <motion.span
                    className={`ml-3 text-sm font-medium z-10 whitespace-nowrap ${isActive ? "text-blue-100" : "text-slate-400 group-hover:text-white"}`}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: isExpanded || isHovered ? 1 : 0, x: isExpanded || isHovered ? 0 : -10 }}
                    transition={{ duration: 0.2 }}
                  >
                    {t(item.k!)}
                  </motion.span>

                  {/* Hover Tooltip (Only when collapsed) */}
                  {!(isExpanded || isHovered) && (
                    <div className="absolute left-full ml-2 px-2 py-1 bg-slate-900 text-white text-xs rounded border border-slate-700 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
                      {t(item.k!)}
                    </div>
                  )}
                </div>
              </Link>
            )
          })}
        </nav>
      </div>

      {/* Footer / User / Settings */}
      <div className="p-4 border-t border-slate-800/50 bg-slate-900/50">
        <div className="flex flex-col gap-2">
            <Link href="/settings">
                <div className="flex items-center h-10 px-3 rounded-md hover:bg-slate-800 cursor-pointer transition-colors">
                    <Settings className="w-5 h-5 text-slate-400 min-w-[1.25rem]" />
                    <motion.span
                        className="ml-3 text-sm text-slate-400 whitespace-nowrap"
                        animate={{ opacity: isExpanded || isHovered ? 1 : 0, width: isExpanded || isHovered ? "auto" : 0 }}
                    >
                        {t("nav.settings_footer")}
                    </motion.span>
                </div>
            </Link>
            
            <button 
                onClick={() => {
                  // Logout logic
                  localStorage.removeItem('token'); 
                  window.location.href='/login'
                }}
                className="flex items-center h-10 px-3 rounded-md hover:bg-red-900/20 group cursor-pointer transition-colors w-full"
            >
                <LogOut className="w-5 h-5 text-slate-400 group-hover:text-red-400 min-w-[1.25rem]" />
                <motion.span
                    className="ml-3 text-sm text-slate-400 group-hover:text-red-400 whitespace-nowrap"
                    animate={{ opacity: isExpanded || isHovered ? 1 : 0, width: isExpanded || isHovered ? "auto" : 0 }}
                >
                    {t("nav.logout")}
                </motion.span>
            </button>
        </div>
      </div>
    </motion.div>
  )
}
