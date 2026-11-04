"use client"
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { apiFetch } from '@/lib/api'

export default function RegisterPage() {
  const router = useRouter()
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    company_name: '',
    sector: 'Manufacturing'
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const r = await apiFetch('/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Não foi possível criar a conta.')
      
      localStorage.setItem('token', data.token)
      localStorage.setItem('user_role', data.role)
      localStorage.setItem('user_id', String(data.user_id))
      
      router.push('/onboarding/kyc')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Não foi possível criar a conta.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Criar conta AuditAI
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Registo seguro para profissionais de auditoria
          </p>
        </div>
        <form className="mt-8 space-y-6" onSubmit={submit}>
          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="name" className="sr-only">Nome completo</label>
              <input
                id="name"
                name="name"
                type="text"
                autoComplete="name"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Nome completo"
                value={formData.name}
                onChange={handleChange}
              />
            </div>
            <div>
              <label htmlFor="email-address" className="sr-only">Email profissional</label>
              <input
                id="email-address"
                name="email"
                type="email"
                autoComplete="email"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Email profissional"
                value={formData.email}
                onChange={handleChange}
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">Palavra-passe</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                minLength={10}
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Palavra-passe (mínimo 10 caracteres)"
                value={formData.password}
                onChange={handleChange}
              />
            </div>
            <div>
              <label htmlFor="company_name" className="sr-only">Empresa ou organização</label>
              <input
                id="company_name"
                name="company_name"
                type="text"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Empresa ou organização"
                value={formData.company_name}
                onChange={handleChange}
              />
            </div>
            <div>
              <label htmlFor="sector" className="sr-only">Setor de atividade</label>
              <select
                id="sector"
                name="sector"
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                value={formData.sector}
                onChange={handleChange}
              >
                <option value="Manufacturing">Indústria</option>
                <option value="Services">Serviços / Consultoria</option>
                <option value="SaaS">Tecnologia (SaaS)</option>
                <option value="Retail">Comércio</option>
                <option value="Financial">Serviços financeiros</option>
                <option value="Public">Setor público</option>
                <option value="Other">Outro</option>
              </select>
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-900 hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              {loading ? 'A criar conta…' : 'Criar conta'}
            </button>
          </div>
          
          {error && (
            <div role="alert" className="text-center text-sm text-red-600 bg-red-50 p-2 rounded">
              {error}
            </div>
          )}
          
          <div className="text-center text-sm">
            <a href="/login" className="font-medium text-blue-600 hover:text-blue-500">
              Já tem conta? Inicie sessão
            </a>
          </div>
        </form>
      </div>
    </div>
  )
}
