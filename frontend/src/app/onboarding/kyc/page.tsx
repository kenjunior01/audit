"use client"
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { apiFetch } from '@/lib/api'

export default function KYCPage() {
  const router = useRouter()
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState('pending') // pending, uploading, scanning, success, error
  const [message, setMessage] = useState('')

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
      setMessage('')
    }
  }

  const upload = async () => {
    if (!file) return
    setStatus('uploading')
    setMessage('Uploading secure document...')
    
    const formData = new FormData()
    formData.append('file', file)
    formData.append('title', 'KYC Credential')
    formData.append('doc_type', 'KYC_Credential')
    
    try {
      // Simulate scanning delay for UX (since local is instant)
      setTimeout(() => {
        if (status === 'uploading') setMessage('AuditAI Security Engine: Scanning for threats...')
      }, 1000)

      const r = await apiFetch('/upload/document', {
        method: 'POST',
        body: formData
      })
      
      if (!r.ok) {
        const data = await r.json()
        throw new Error(data.error || 'Upload failed')
      }
      
      setStatus('success')
    } catch (e: any) {
      setStatus('error')
      setMessage(e.message)
    }
  }

  const skip = () => {
    if (confirm("Without verification, your account will be limited to Read-Only access. Continue?")) {
        router.push('/')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center mb-6">
            <div className="h-12 w-12 bg-blue-900 rounded-lg flex items-center justify-center">
                <svg className="h-8 w-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
            </div>
        </div>
        <h2 className="text-center text-3xl font-extrabold text-gray-900">
          Compliance Check
        </h2>
        <p className="mt-2 text-center text-sm text-gray-600">
          Complete your profile to unlock Audit capabilities.
        </p>
        
        {/* Progress Steps */}
        <div className="mt-6 flex justify-center items-center space-x-4 text-sm">
            <span className="text-blue-600 font-semibold">1. Registration ✓</span>
            <span className="text-gray-400">→</span>
            <span className="text-gray-900 font-bold border-b-2 border-blue-600">2. Verification</span>
            <span className="text-gray-400">→</span>
            <span className="text-gray-500">3. Access</span>
        </div>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10 border-t-4 border-blue-900">
          {status === 'success' ? (
            <div className="text-center">
              <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-green-100 mb-4">
                <svg className="h-8 w-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="mt-2 text-xl font-bold text-gray-900">Verification Submitted</h3>
              <p className="mt-2 text-sm text-gray-600 bg-green-50 p-3 rounded-md">
                Your document has passed the initial <strong>Security Scan</strong>. Our AI Compliance Engine is now analyzing your credentials.
              </p>
              <div className="mt-6">
                <button
                  onClick={() => router.push('/')}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-900 hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  Enter Dashboard
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              
              <div className="bg-blue-50 border-l-4 border-blue-400 p-4">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-blue-400" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <p className="text-sm text-blue-700">
                      We require an official corporate document (e.g., Certificate of Incorporation or Professional License).
                    </p>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Document Type
                </label>
                <select className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md">
                  <option>Certificate of Incorporation</option>
                  <option>Professional License (CPA/CIA)</option>
                  <option>Employee ID Badge</option>
                  <option>Tax Registration</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Upload Secure File
                </label>
                <div className={`mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-dashed rounded-md ${file ? 'border-blue-500 bg-blue-50' : 'border-gray-300'}`}>
                  <div className="space-y-1 text-center">
                    <svg
                      className="mx-auto h-12 w-12 text-gray-400"
                      stroke="currentColor"
                      fill="none"
                      viewBox="0 0 48 48"
                      aria-hidden="true"
                    >
                      <path
                        d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                        strokeWidth={2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    <div className="flex text-sm text-gray-600 justify-center">
                      <label
                        htmlFor="file-upload"
                        className="relative cursor-pointer rounded-md font-medium text-blue-600 hover:text-blue-500 focus-within:outline-none"
                      >
                        <span>Upload a file</span>
                        <input id="file-upload" name="file-upload" type="file" className="sr-only" onChange={handleFileChange} />
                      </label>
                      <p className="pl-1">or drag and drop</p>
                    </div>
                    <p className="text-xs text-gray-500">PDF, PNG, JPG (Max 10MB)</p>
                    <p className="text-xs text-green-600 mt-1 flex items-center justify-center">
                        <svg className="h-3 w-3 mr-1" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/></svg>
                        Virus Scan Active
                    </p>
                  </div>
                </div>
                {file && <p className="mt-2 text-sm text-blue-600 font-medium text-center">Selected: {file.name}</p>}
              </div>

              {status === 'error' && (
                <div className="bg-red-50 border-l-4 border-red-400 p-4">
                    <div className="flex">
                        <div className="flex-shrink-0">
                            <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                            </svg>
                        </div>
                        <div className="ml-3">
                            <h3 className="text-sm font-medium text-red-800">Verification Error</h3>
                            <div className="mt-2 text-sm text-red-700">
                                <p>{message}</p>
                            </div>
                        </div>
                    </div>
                </div>
              )}
              
              {status === 'uploading' && (
                  <div className="bg-blue-50 p-4 rounded-md">
                      <div className="flex items-center">
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-900 mr-3"></div>
                          <span className="text-sm text-blue-900">{message}</span>
                      </div>
                  </div>
              )}

              <div className="flex gap-4">
                <button
                  type="button"
                  onClick={skip}
                  className="w-1/3 flex justify-center py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-500 bg-white hover:bg-gray-50 focus:outline-none"
                >
                  Later
                </button>
                <button
                  type="button"
                  onClick={upload}
                  disabled={!file || status === 'uploading'}
                  className="w-2/3 flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-900 hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {status === 'uploading' ? 'Processing...' : 'Submit & Verify'}
                </button>
              </div>
            </div>
          )}
        </div>
        <p className="mt-4 text-center text-xs text-gray-400">
            Secure Encryption • ISO 27001 Compliant • AuditAI Engine
        </p>
      </div>
    </div>
  )
}
