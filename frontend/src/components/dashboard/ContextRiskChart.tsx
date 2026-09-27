"use client"

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { AlertTriangle, Users, Settings } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import AISettingsModal from './AISettingsModal';

export default function ContextRiskChart() {
    const [data, setData] = useState<any>(null);
    const [settings, setSettings] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [showSettings, setShowSettings] = useState(false);
    const [viewMode, setViewMode] = useState<'department' | 'category'>('department');
    const router = useRouter();

    const fetchData = async () => {
        try {
            const res = await apiFetch('/context/risk-stats');
            if (res.ok) {
                const json = await res.json();
                setData(json);
            }
        } catch (error) {
            console.error("Failed to fetch context stats", error);
        }
    };

    const fetchSettings = async () => {
        try {
            const res = await apiFetch('/settings/integration/current/');
            if (res.ok) {
                setSettings(await res.json());
            }
        } catch (error) {
            console.error("Failed to fetch settings", error);
        }
    };

    useEffect(() => {
        Promise.all([fetchData(), fetchSettings()]).finally(() => setLoading(false));
    }, []);

    const handleBarClick = (entry: any) => {
        if (entry) {
            if (viewMode === 'department' && entry.department) {
                router.push(`/alerts?department=${encodeURIComponent(entry.department)}`);
            } else if (viewMode === 'category' && entry.category) {
                router.push(`/alerts?category=${encodeURIComponent(entry.category)}`);
            }
        }
    };

    const sensitivity = settings?.ai_sensitivity ?? 0.5;
    // Dynamic thresholds based on sensitivity (0.0 - 1.0)
    // S=0.0 (Conservative): High > 90, Med > 60
    // S=0.5 (Normal): High > 70, Med > 40
    // S=1.0 (Aggressive): High > 50, Med > 20
    const highThreshold = 90 - (sensitivity * 40);
    const mediumThreshold = 60 - (sensitivity * 40);

    if (loading) return <div className="h-64 flex items-center justify-center text-sm text-gray-500">Carregando análise...</div>;
    
    // If no data or empty departments, don't show chart
    if (!data || !data.departments || data.departments.length === 0) {
         return null; 
    }

    return (
        <>
            <Card className="h-full shadow-sm border-slate-200">
                <CardHeader className="pb-2 flex flex-row items-center justify-between">
                    <CardTitle className="text-lg font-semibold flex items-center gap-2 text-slate-800">
                        <Users className="h-5 w-5 text-blue-600" />
                        Risco por {viewMode === 'department' ? 'Departamento' : 'Categoria'}
                    </CardTitle>
                    <div className="flex gap-2">
                        <div className="flex bg-slate-100 rounded-lg p-1">
                            <button 
                                onClick={() => setViewMode('department')}
                                className={`px-2 py-1 text-xs font-medium rounded-md transition-all ${viewMode === 'department' ? 'bg-white shadow text-slate-800' : 'text-slate-500 hover:text-slate-700'}`}
                            >
                                Dept
                            </button>
                            <button 
                                onClick={() => setViewMode('category')}
                                className={`px-2 py-1 text-xs font-medium rounded-md transition-all ${viewMode === 'category' ? 'bg-white shadow text-slate-800' : 'text-slate-500 hover:text-slate-700'}`}
                            >
                                Categ
                            </button>
                        </div>
                        <button 
                            onClick={() => setShowSettings(true)}
                            className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                            title="Configurações da IA"
                        >
                            <Settings className="w-4 h-4" />
                        </button>
                    </div>
                </CardHeader>
                <CardContent>
                <div className="h-[200px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart 
                            data={viewMode === 'department' ? data.departments : data.categories} 
                            layout="vertical" 
                            margin={{ left: 40, right: 20, top: 10, bottom: 10 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#e2e8f0" />
                            <XAxis type="number" domain={[0, 100]} hide />
                            <YAxis 
                                dataKey={viewMode === 'department' ? 'department' : 'category'} 
                                type="category" 
                                width={100} 
                                tick={{fontSize: 12, fill: '#64748b'}} 
                                axisLine={false}
                                tickLine={false}
                            />
                            <Tooltip 
                                formatter={(value: any) => [`${value}%`, 'Score de Risco']}
                                contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                cursor={{fill: 'transparent'}}
                            />
                            <Bar 
                                dataKey="risk_score" 
                                radius={[0, 4, 4, 0]} 
                                barSize={24}
                                onClick={handleBarClick}
                                style={{ cursor: 'pointer' }}
                            >
                                {(viewMode === 'department' ? data.departments : (data.categories || [])).map((entry: any, index: number) => (
                                    <Cell 
                                        key={`cell-${index}`} 
                                        fill={entry.risk_score > highThreshold ? '#ef4444' : entry.risk_score > mediumThreshold ? '#f59e0b' : '#10b981'}
                                        style={{ cursor: 'pointer' }}
                                    />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
                
                {data.references && data.references.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-slate-100">
                        <h4 className="text-xs font-semibold mb-2 flex items-center gap-1.5 text-slate-600 uppercase tracking-wider">
                            <AlertTriangle className="h-3 w-3 text-amber-500" />
                            Listas Críticas
                        </h4>
                        <div className="flex flex-wrap gap-2">
                            {data.references.slice(0, 4).map((ref: any, idx: number) => (
                                <div key={idx} className="bg-slate-50 px-2 py-1 rounded text-xs border border-slate-100 flex items-center gap-2">
                                    <span className="font-medium text-slate-700">{ref.name}</span>
                                    {ref.high_risk_items > 0 && (
                                        <span className="bg-red-100 text-red-700 px-1.5 rounded-full text-[10px] font-bold">
                                            {ref.high_risk_items}
                                        </span>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
        <AISettingsModal 
            isOpen={showSettings} 
            onClose={() => setShowSettings(false)} 
            onSave={() => { fetchSettings(); fetchData(); }}
        />
    </>
    );
}
