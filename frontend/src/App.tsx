import { useState, useEffect } from 'react'
import { getCurrentUser } from 'aws-amplify/auth'
import LoginPage from './components/LoginPage'
import Dashboard from './components/Dashboard'

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)

  useEffect(() => {
    getCurrentUser()
      .then(() => setAuthed(true))
      .catch(() => setAuthed(false))
  }, [])

  if (authed === null) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center">
        <div className="text-slate-500 text-xs animate-pulse">Initialising...</div>
      </div>
    )
  }

  if (!authed) {
    return <LoginPage onLogin={() => setAuthed(true)} />
  }

  return <Dashboard onSignOut={() => setAuthed(false)} />
}
