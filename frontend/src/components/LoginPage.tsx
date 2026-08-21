import { useState } from 'react'
import { signIn } from 'aws-amplify/auth'

interface Props {
  onLogin: () => void
}

export default function LoginPage({ onLogin }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await signIn({ username, password })
      onLogin()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center">
      <div className="panel w-full max-w-sm space-y-6">
        <div className="text-center">
          <div className="text-accent text-2xl font-semibold tracking-widest uppercase">PaintShop</div>
          <div className="text-slate-400 text-xs mt-1 tracking-wider">Control Center</div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-slate-400 text-xs mb-1 uppercase tracking-wider">Username</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="w-full bg-surface border border-border rounded px-3 py-2 text-slate-100 focus:outline-none focus:border-accent"
              required
            />
          </div>
          <div>
            <label className="block text-slate-400 text-xs mb-1 uppercase tracking-wider">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full bg-surface border border-border rounded px-3 py-2 text-slate-100 focus:outline-none focus:border-accent"
              required
            />
          </div>

          {error && <div className="text-red-400 text-xs">{error}</div>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent/10 border border-accent text-accent rounded py-2 text-sm hover:bg-accent/20 transition disabled:opacity-50"
          >
            {loading ? 'Authenticating...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
