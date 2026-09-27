/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const base = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000'
    return [
      { source: '/api/:path*', destination: `${base}/django/api/:path*` },
      { source: '/media/:path*', destination: `${base}/django/media/:path*` },
    ]
  }
}

export default nextConfig
