import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, Bot, Landmark, LayoutDashboard, LogOut, Siren, Workflow, X } from 'lucide-react'
import { api, auth, formatTime, wsUrl } from './api'
import { useChat } from './useChat'
import Login from './components/Login'
import Dashboard from './components/Dashboard'
import ChatPanel from './components/ChatPanel'
import AgentTrace from './components/AgentTrace'

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(!!auth.token)

  useEffect(() => {
    if (!auth.token) return
    api.get('/api/auth/me').then(setUser).catch(() => { auth.token = null }).finally(() => setChecking(false))
  }, [])

  useEffect(() => {
    const logout = () => { auth.token = null; setUser(null) }
    window.addEventListener('smartbank:logout', logout)
    return () => window.removeEventListener('smartbank:logout', logout)
  }, [])

  if (checking) return null
  if (!user) return <Login onLogin={setUser} />
  return <Bank key={user.email} user={user} onLogout={() => { auth.token = null; setUser(null) }} />
}

function Bank({ user, onLogout }) {
  const [overview, setOverview] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [freshIds, setFreshIds] = useState(new Set())
  const [toasts, setToasts] = useState([])
  const [alerts, setAlerts] = useState(null)
  const [connected, setConnected] = useState(false)
  const [draft, setDraft] = useState('')
  const [view, setView] = useState('chat')   // which panel is visible on narrow screens
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(() => {
    api.get('/api/overview').then(setOverview).catch(() => {})
    api.get('/api/transactions?limit=25').then(setTransactions).catch(() => {})
  }, [])
  useEffect(refresh, [refresh])

  const chat = useChat(user, refresh)

  // ---- live updates over WebSocket (with automatic reconnect) ----
  const toastId = useRef(0)
  useEffect(() => {
    let ws, retry, closed = false
    const connect = () => {
      ws = new WebSocket(wsUrl())
      ws.onopen = () => ws.send(JSON.stringify({ token: auth.token }))
      ws.onclose = (e) => {
        setConnected(false)
        if (e.code === 4401) { window.dispatchEvent(new Event('smartbank:logout')); return }  // session expired
        if (!closed) retry = setTimeout(connect, 3000)
      }
      ws.onmessage = (msg) => {
        const { type, data } = JSON.parse(msg.data)
        if (type === 'ready') setConnected(true)
        else if (type === 'transaction') {
          setTransactions((ts) => [data, ...ts.filter((t) => t.id !== data.id)].slice(0, 40))
          setFreshIds((s) => new Set(s).add(data.id))
        } else if (type === 'accounts') {
          setOverview((o) => (o ? { ...o, accounts: data } : o))
        } else if (type === 'alert') {
          const id = ++toastId.current
          setToasts((t) => [...t, { ...data, toastId: id }])
          if (data.severity !== 'CRITICAL') setTimeout(() => setToasts((t) => t.filter((x) => x.toastId !== id)), 8000)
          api.get('/api/overview').then(setOverview).catch(() => {})
        }
      }
    }
    connect()
    const ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25000)
    return () => { closed = true; clearTimeout(retry); clearInterval(ping); ws?.close() }
  }, [])

  const ask = (text) => { setDraft(text); setView('chat') }

  async function simulate(suspicious) {
    setBusy(true)
    try { await api.post('/api/demo/simulate', { suspicious }) } finally { setBusy(false) }
  }
  async function resetCards() {
    setBusy(true)
    try { await api.post('/api/demo/reset-cards'); refresh() } finally { setBusy(false) }
  }
  async function toggleAlerts() {
    if (alerts) return setAlerts(null)
    setAlerts(await api.get('/api/alerts'))
    await api.post('/api/alerts/read-all')
    setOverview((o) => (o ? { ...o, unread_alerts: 0 } : o))
  }

  const traceSteps = chat.traces[chat.activeTurn] || []
  const panel = (name) => (view === name ? 'block' : 'hidden') + ' xl:block'

  return (
    <div className="h-full flex flex-col">
      <header className="h-14 shrink-0 border-b border-line bg-white flex items-center gap-3 px-4">
        <div className="flex items-center gap-2 font-semibold text-brand-700">
          <span className="grid place-items-center size-8 rounded-lg bg-brand-700 text-white"><Landmark size={17} /></span>
          <span className="hidden sm:inline">SmartBank AI</span>
        </div>
        <span title={connected ? 'Live updates connected' : 'Reconnecting…'}
          className={`ml-1 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${connected ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-muted'}`}>
          <span className={`size-1.5 rounded-full ${connected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
          {connected ? 'Live' : 'Offline'}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <button onClick={toggleAlerts} aria-label="Alerts" className="relative grid place-items-center size-9 rounded-lg hover:bg-slate-100">
              <Bell size={18} />
              {overview?.unread_alerts > 0 && (
                <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-red-600 text-white text-[10px] font-semibold grid place-items-center">
                  {overview.unread_alerts}
                </span>
              )}
            </button>
            {alerts && (
              <div className="absolute right-0 top-11 z-30 w-[min(22rem,calc(100vw-2rem))] max-h-96 overflow-y-auto rounded-xl border border-line bg-white shadow-xl p-2">
                {alerts.length === 0 && <p className="p-3 text-sm text-muted">No alerts.</p>}
                {alerts.map((a) => (
                  <div key={a.id} className="rounded-lg p-2.5 hover:bg-slate-50">
                    <p className={`text-sm font-medium ${a.severity === 'CRITICAL' ? 'text-red-700' : ''}`}>{a.title}</p>
                    <p className="text-xs text-muted mt-0.5">{a.message}</p>
                    <p className="text-[10px] text-muted mt-1">{formatTime(a.created_at)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="hidden sm:block text-right leading-tight">
            <p className="text-sm font-medium">{user.name}</p>
            <p className="text-[11px] text-muted">{user.email}</p>
          </div>
          <button onClick={onLogout} aria-label="Log out" className="grid place-items-center size-9 rounded-lg hover:bg-slate-100"><LogOut size={18} /></button>
        </div>
      </header>

      {/* tabs for narrow screens */}
      <nav className="xl:hidden grid grid-cols-3 gap-1 p-2 bg-white border-b border-line text-sm">
        {[['dashboard', LayoutDashboard, 'Dashboard'], ['chat', Bot, 'Assistant'], ['trace', Workflow, 'Agent trace']].map(([key, Icon, label]) => (
          <button key={key} onClick={() => setView(key)}
            className={`flex items-center justify-center gap-1.5 rounded-lg py-1.5 font-medium ${view === key ? 'bg-brand-50 text-brand-700' : 'text-muted'}`}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </nav>

      <main className="flex-1 min-h-0 grid grid-rows-[minmax(0,1fr)] xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_minmax(0,0.75fr)] gap-4 p-4">
        <div className={`${panel('dashboard')} min-h-0 overflow-y-auto pr-1`}>
          <Dashboard overview={overview} transactions={transactions} freshIds={freshIds} busy={busy}
            onAsk={ask} onSimulate={simulate} onResetCards={resetCards} />
        </div>
        <div className={`${panel('chat')} min-h-0 h-full`}>
          <ChatPanel chat={chat} draft={draft} setDraft={setDraft} onShowTrace={() => setView('trace')} />
        </div>
        <div className={`${panel('trace')} min-h-0 h-full`}>
          <AgentTrace steps={traceSteps} running={chat.streaming} />
        </div>
      </main>

      {/* live alert toasts */}
      <div className="fixed top-16 right-4 z-40 space-y-2 w-[min(24rem,calc(100vw-2rem))]">
        {toasts.map((t) => (
          <div key={t.toastId} role="alert"
            className={`animate-slide-in rounded-xl border shadow-lg p-3 bg-white ${t.severity === 'CRITICAL' ? 'border-red-300' : 'border-line'}`}>
            <div className="flex gap-2">
              <Siren size={18} className={t.severity === 'CRITICAL' ? 'text-red-600 shrink-0' : 'text-brand-700 shrink-0'} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold">{t.title}</p>
                <p className="text-xs text-muted mt-0.5">{t.message}</p>
                {t.type === 'FRAUD' && (
                  <button onClick={() => { ask('I just got a fraud alert about a transaction I did not make. What happened and what should I do?'); setToasts((x) => x.filter((y) => y.toastId !== t.toastId)) }}
                    className="mt-2 text-xs font-medium text-red-700 hover:underline">Ask the assistant →</button>
                )}
              </div>
              <button aria-label="Dismiss" onClick={() => setToasts((x) => x.filter((y) => y.toastId !== t.toastId))} className="text-muted hover:text-ink self-start">
                <X size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
