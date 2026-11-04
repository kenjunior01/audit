"use client"
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { apiFetch } from '@/lib/api'

export default function LoginPage() {
  const router = useRouter()
  const [formData, setFormData] = useState({
    email: '',
    password: ''
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const r = await apiFetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Email ou palavra-passe inválidos.')
      
      localStorage.setItem('token', data.token)
      localStorage.setItem('user_role', data.role)
      localStorage.setItem('user_id', String(data.user_id))
      
      router.push('/')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Não foi possível iniciar sessão.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Iniciar sessão no AuditAI
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Ainda não tem conta? <a href="/register" className="font-medium text-blue-600 hover:text-blue-500">Registe a sua organização</a>
          </p>
        </div>
        <form className="mt-8 space-y-6" onSubmit={submit}>
          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="email-address" className="sr-only">Endereço de email</label>
              <input
                id="email-address"
                name="email"
                type="email"
                autoComplete="email"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Endereço de email"
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
                autoComplete="current-password"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Palavra-passe"
                value={formData.password}
                onChange={handleChange}
              />
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-900 hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              {loading ? 'A iniciar sessão…' : 'Iniciar sessão'}
            </button>
          </div>
          
          {error && (
            <div role="alert" className="text-center text-sm text-red-600 bg-red-50 p-2 rounded">
              {error}
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
