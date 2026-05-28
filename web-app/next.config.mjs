/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  allowedDevOrigins: ['100.102.17.12'],
  async rewrites() {
    if (process.env.NODE_ENV !== 'production') {
      return [
        { source: '/api/:path*', destination: 'http://localhost:2727/:path*' },
      ]
    }
    return []
  },
}

export default nextConfig
