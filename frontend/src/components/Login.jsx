import { useEffect, useState } from 'react'
import { Bot, Landmark, LoaderCircle, Lock, ShieldCheck, Sparkles } from 'lucide-react'
import { api, auth } from '../api'

// Fictional demo accounts all share this password (also documented in the README).
const DEMO_PASSWORD = 'SmartBank@2026'

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [demo, setDemo] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.get('/api/auth/demo-accounts').then(setDemo).catch(() => {}) }, [])

  async function submit(e, creds = { email, password }) {
    e?.preventDefault()
    setBusy(true)
    setError('')
    try {
      const res = await api.post('/api/auth/login', creds)
      auth.token = res.token
      onLogin(res.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-full grid lg:grid-cols-[1.1fr_1fr]">
      {/* brand / explainer panel */}
      <section className="hidden lg:flex flex-col justify-between bg-brand-900 text-white p-12 relative overflow-hidden">
        <div className="absolute -right-24 -top-24 size-96 rounded-full bg-brand-700/40" />
        <div className="absolute -left-16 bottom-10 size-72 rounded-full bg-brand-600/20" />
        <div className="relative flex items-center gap-3 text-xl font-semibold">
          <span className="grid place-items-center size-10 rounded-xl bg-white/10"><Landmark size={22} /></span>
          SmartBank AI
        </div>
        <div className="relative max-w-md">
          <h1 className="text-4xl font-semibold leading-tight">Banking with a team of AI agents.</h1>
          <p className="mt-4 text-brand-100/80 leading-relaxed">
            A supervisor agent understands your request and hands it to specialists for accounts, fraud,
            credit and bank policy. Every number comes from the bank's systems. Every sensitive action waits for you.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-brand-100/90">
            <li className="flex gap-3"><Bot size={18} className="shrink-0" /> Multi-agent orchestration with LangGraph + Gemini</li>
            <li className="flex gap-3"><ShieldCheck size={18} className="shrink-0" /> Real-time fraud scoring and human-in-the-loop approvals</li>
            <li className="flex gap-3"><Sparkles size={18} className="shrink-0" /> Policy answers with citations (hybrid RAG)</li>
          </ul>
        </div>
        <p className="relative text-xs text-brand-100/60">Simulated bank · fictional customers and data</p>
      </section>

      {/* login form */}
      <section className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-2 text-lg font-semibold text-brand-700 mb-8">
            <Landmark size={22} /> SmartBank AI
          </div>
          <h2 className="text-2xl font-semibold">Sign in</h2>
          <p className="text-muted text-sm mt-1">Use one of the demo customers below.</p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <label className="block">
              <span className="text-sm font-medium">Email</span>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2.5 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" />
            </label>
            <label className="block">
              <span className="text-sm font-medium">Password</span>
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2.5 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" />
            </label>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button disabled={busy}
              className="w-full rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-medium py-2.5 flex items-center justify-center gap-2 disabled:opacity-60">
              {busy ? <LoaderCircle size={18} className="animate-spin" /> : <Lock size={16} />} Sign in
            </button>
          </form>

          {demo.length > 0 && (
            <div className="mt-8">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                Demo customers · password <span className="font-mono normal-case text-ink">{DEMO_PASSWORD}</span>
              </p>
              <div className="mt-3 grid sm:grid-cols-2 gap-2">
                {demo.map((d) => (
                  <button key={d.email} type="button" disabled={busy}
                    onClick={() => { setEmail(d.email); setPassword(DEMO_PASSWORD); submit(null, { email: d.email, password: DEMO_PASSWORD }) }}
                    className="text-left rounded-lg border border-line bg-white p-3 hover:border-brand-500 hover:bg-brand-50 transition">
                    <div className="font-medium text-sm">{d.name}</div>
                    <div className="text-xs text-muted mt-0.5">{d.scenario}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
