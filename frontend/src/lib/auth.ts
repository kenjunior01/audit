'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getToken } from '@/lib/api'

/** Hook de guarda de sessão: redireciona para /login se não houver token. */
export function useRequireToken(): boolean {
  const router = useRouter()
  const [hasToken, setHasToken] = useState(false)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      router.replace('/login')
    } else {
      setHasToken(true)
    }
  }, [router])

  return hasToken
}
