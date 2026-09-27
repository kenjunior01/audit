"use client"
import '../styles/globals.css'
import type { ReactNode } from 'react'
import { CommandDock } from '@/components/layout/CommandDock'

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-br">
      <body className="bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100">
        <div className="min-h-screen flex">
          {/* New Command Dock Sidebar */}
          <CommandDock />
          
          {/* Main Content Area */}
          <main className="flex-1 ml-[4.5rem] transition-all duration-300 relative">
            {/* Top Bar for Context/Actions (Optional, keeping minimal) */}
            <header className="h-16 border-b border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm flex items-center justify-between px-8 sticky top-0 z-40">
              <div className="flex items-center gap-4">
                 <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600">
                    Audit Command Center
                 </h1>
              </div>
              <div className="flex items-center gap-4">
                 <div className="text-sm text-slate-500">
                    System Status: <span className="text-emerald-500 font-medium">Online</span>
                 </div>
                 {/* Legacy Token Input (Hidden or minimized) */}
                 <div className="hidden">
                    <input id="token" placeholder="Bearer token" className="border p-2 text-sm" />
                 </div>
              </div>
            </header>

            <div className="p-8 max-w-[1600px] mx-auto">
                {children}
            </div>
          </main>
        </div>
      </body>
    </html>
  )
}
