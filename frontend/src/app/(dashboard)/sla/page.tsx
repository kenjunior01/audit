'use client'

import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from 'recharts'
import { Clock, AlertTriangle, CheckCircle, Users, TrendingUp } from 'lucide-react'

export default function SLAPage() {
    const [stats, setStats] = useState<any>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        apiFetch('/cases/sla-stats')
            .then(r => r.json())
            .then(data => setStats(data))
            .catch(err => console.error(err))
            .finally(() => setLoading(false))
    }, [])

    if (loading) return <div className="p-8 text-center text-slate-500">Carregando métricas de SLA...</div>

    const processedAuditorStats = stats?.auditor_stats?.map((s: any) => ({
        ...s,
        name: s.assigned_to || 'Não Atribuído',
        active_on_time: Math.max(0, s.total - s.closed - s.overdue)
    })) || []

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Gerenciamento de SLA</h1>
                    <p className="text-slate-500">Métricas de desempenho e cumprimento de prazos da equipe de auditoria.</p>
                </div>
                <div className="flex items-center gap-2 bg-slate-100 px-3 py-1 rounded-full text-sm font-medium text-slate-600">
                    <Clock className="h-4 w-4" />
                    Atualizado: Hoje
                </div>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card className="border-l-4 border-l-blue-500 shadow-sm">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-slate-500 flex items-center gap-2">
                            <Clock className="h-4 w-4" /> Tempo Médio
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-slate-900">{stats?.avg_resolution_hours}h</div>
                        <p className="text-xs text-slate-500 mt-1">Para resolução de casos</p>
                    </CardContent>
                </Card>

                <Card className="border-l-4 border-l-green-500 shadow-sm">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-slate-500 flex items-center gap-2">
                            <CheckCircle className="h-4 w-4" /> Compliance Rate
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-slate-900">{stats?.compliance_rate}%</div>
                        <p className="text-xs text-slate-500 mt-1">Casos dentro do prazo</p>
                    </CardContent>
                </Card>

                <Card className="border-l-4 border-l-red-500 shadow-sm">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-slate-500 flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4" /> Violações
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-red-600">{stats?.total_breaches}</div>
                        <p className="text-xs text-slate-500 mt-1">Casos estourados</p>
                    </CardContent>
                </Card>

                <Card className="border-l-4 border-l-amber-500 shadow-sm">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-slate-500 flex items-center gap-2">
                            <TrendingUp className="h-4 w-4" /> Atraso Ativo
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-amber-600">{stats?.active_overdue}</div>
                        <p className="text-xs text-slate-500 mt-1">Casos abertos vencidos</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Auditor Performance Chart */}
                <Card className="shadow-sm">
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <Users className="h-5 w-5 text-indigo-600" />
                            Carga de Trabalho por Auditor
                        </CardTitle>
                        <CardDescription>Distribuição de casos Fechados, Em Andamento e Atrasados</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={processedAuditorStats} layout="vertical" margin={{ left: 40, right: 20 }}>
                                    <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#e2e8f0" />
                                    <XAxis type="number" hide />
                                    <YAxis 
                                        dataKey="name" 
                                        type="category" 
                                        width={100} 
                                        tick={{fontSize: 12, fill: '#64748b'}} 
                                        axisLine={false}
                                        tickLine={false}
                                    />
                                    <Tooltip 
                                        cursor={{fill: '#f1f5f9'}}
                                        contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                    />
                                    <Legend />
                                    <Bar dataKey="closed" name="Fechados" stackId="a" fill="#10b981" barSize={24} radius={[0, 0, 0, 0]} />
                                    <Bar dataKey="active_on_time" name="Em Dia" stackId="a" fill="#cbd5e1" barSize={24} radius={[0, 0, 0, 0]} />
                                    <Bar dataKey="overdue" name="Em Atraso" stackId="a" fill="#ef4444" barSize={24} radius={[0, 4, 4, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>

                {/* Compliance Pie Chart */}
                <Card className="shadow-sm">
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <CheckCircle className="h-5 w-5 text-green-600" />
                            Status Geral de Conformidade
                        </CardTitle>
                        <CardDescription>Percentual de casos atendidos dentro do SLA</CardDescription>
                    </CardHeader>
                    <CardContent className="flex justify-center items-center">
                        <div className="h-[300px] w-full max-w-[400px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={[
                                            { name: 'No Prazo', value: (stats?.compliance_rate || 0) },
                                            { name: 'Em Atraso', value: Math.max(0, 100 - (stats?.compliance_rate || 0)) }
                                        ]}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={80}
                                        outerRadius={100}
                                        paddingAngle={5}
                                        dataKey="value"
                                    >
                                        <Cell fill="#10b981" />
                                        <Cell fill="#ef4444" />
                                    </Pie>
                                    <Tooltip formatter={(val: any) => `${val.toFixed(1)}%`} />
                                    <Legend verticalAlign="bottom" height={36} />
                                    <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" className="fill-slate-900 text-2xl font-bold">
                                        {stats?.compliance_rate}%
                                    </text>
                                    <text x="50%" y="58%" textAnchor="middle" dominantBaseline="middle" className="fill-slate-500 text-xs">
                                        Compliance
                                    </text>
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
