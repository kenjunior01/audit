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
      if (!r.ok) throw new Error(data.error || 'Registration failed')
      
      // Store token
      localStorage.setItem('token', data.token)
      localStorage.setItem('user_role', data.role)
      localStorage.setItem('user_id', data.user_id)
      
      // Redirect to KYC
      router.push('/onboarding/kyc')
    } catch (e: any) {
      setError(e?.message || 'Error registering')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            AuditAI Corporate Access
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Secure registration for audit professionals
          </p>
        </div>
        <form className="mt-8 space-y-6" onSubmit={submit}>
          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="name" className="sr-only">Full Name</label>
              <input
                id="name"
                name="name"
                type="text"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Full Name"
                value={formData.name}
                onChange={handleChange}
              />
            </div>
            <div>
              <label htmlFor="email-address" className="sr-only">Work Email</label>
              <input
                id="email-address"
                name="email"
                type="email"
                autoComplete="email"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Work Email Address"
                value={formData.email}
                onChange={handleChange}
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Strong Password"
                value={formData.password}
                onChange={handleChange}
              />
            </div>
            <div>
              <label htmlFor="company_name" className="sr-only">Company Name</label>
              <input
                id="company_name"
                name="company_name"
                type="text"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Organization / Company Name"
                value={formData.company_name}
                onChange={handleChange}
              />
            </div>
            <div>
              <label htmlFor="sector" className="sr-only">Sector</label>
              <select
                id="sector"
                name="sector"
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                value={formData.sector}
                onChange={handleChange}
              >
                <option value="Manufacturing">Manufacturing</option>
                <option value="Services">Services / Consulting</option>
                <option value="SaaS">Technology (SaaS)</option>
                <option value="Retail">Retail</option>
                <option value="Financial">Financial Services</option>
                <option value="Public">Public Sector</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-900 hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              {loading ? 'Processing...' : 'Create Corporate Account'}
            </button>
          </div>
          
          {error && (
            <div className="text-center text-sm text-red-600 bg-red-50 p-2 rounded">
              {error}
            </div>
          )}
          
          <div className="text-center text-sm">
            <a href="/login" className="font-medium text-blue-600 hover:text-blue-500">
              Already have an account? Sign in
            </a>
          </div>
        </form>
      </div>
    </div>
  )
}
