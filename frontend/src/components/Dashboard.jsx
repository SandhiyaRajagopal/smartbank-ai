import { Activity, CreditCard, FlaskConical, Gauge, Landmark, MessageSquare, PieChart, RotateCcw, Siren, Wallet, Zap } from 'lucide-react'
import { formatINR, formatTime } from '../api'
import { Card, RiskBadge } from './ui'

export default function Dashboard({ overview, transactions, freshIds, onAsk, onSimulate, onResetCards, busy }) {
  if (!overview) return <div className="p-6 text-muted text-sm">Loading your accounts…</div>
  const { profile, accounts, cards, credit, loans, spending } = overview
  const total = accounts.reduce((s, a) => s + a.balance, 0)

  return (
    <div className="space-y-4">
      {/* balance hero */}
      <section className="rounded-2xl bg-gradient-to-br from-brand-900 to-brand-700 text-white p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-brand-100/80 text-sm">Total balance</p>
            <p className="text-3xl font-semibold mt-1 tabular-nums">{formatINR(total)}</p>
            <p className="text-xs text-brand-100/70 mt-1">
              {accounts.map((a) => `${a.type} ${a.account_number}`).join(' · ')}
            </p>
          </div>
          <Wallet className="text-brand-100/60" />
        </div>
        <div className="grid grid-cols-3 gap-3 mt-5 text-sm">
          <Stat label="Spent (30d)" value={formatINR(spending.total_spent)} />
          <Stat label="Received (30d)" value={formatINR(spending.total_received)} />
          <Stat label="KYC" value={profile.kyc_status} warn={profile.kyc_status !== 'VERIFIED'} />
        </div>
      </section>

      <div className="grid sm:grid-cols-2 gap-4">
        <Card title="Cards" icon={CreditCard}>
          <ul className="space-y-2">
            {cards.map((c) => (
              <li key={c.id} className="flex items-center justify-between rounded-xl border border-line px-3 py-2">
                <div>
                  <p className="text-sm font-medium">{c.network} {c.type.toLowerCase()}</p>
                  <p className="text-xs text-muted font-mono">{c.number}</p>
                </div>
                <span className={`text-[11px] font-semibold rounded-full px-2 py-0.5 ${c.status === 'ACTIVE' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                  {c.status}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Credit score" icon={Gauge}>
          {credit.score ? (
            <>
              <div className="flex items-end gap-2">
                <span className="text-3xl font-semibold tabular-nums">{credit.score}</span>
                <span className="text-sm text-muted mb-1">/ 900 · {credit.band}</span>
              </div>
              <div className="mt-3 h-2 rounded-full bg-gradient-to-r from-red-400 via-amber-300 to-emerald-500 relative">
                <span className="absolute -top-1 size-4 rounded-full bg-white border-2 border-ink"
                  style={{ left: `calc(${((credit.score - 300) / 600) * 100}% - 8px)` }} />
              </div>
              <p className="text-xs text-muted mt-3">
                {credit.missed_payments_last_12m} missed payments · {Math.round(credit.credit_utilisation * 100)}% utilisation
              </p>
            </>
          ) : (
            <p className="text-sm text-muted">No credit history with the bureau yet.</p>
          )}
        </Card>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <Card title="Spending · last 30 days" icon={PieChart}>
          <ul className="space-y-2">
            {spending.by_category.slice(0, 6).map((c) => (
              <li key={c.category}>
                <div className="flex justify-between text-xs">
                  <span className="font-medium">{c.category}</span>
                  <span className="tabular-nums text-muted">{formatINR(c.amount)}</span>
                </div>
                <div className="h-1.5 rounded-full bg-slate-100 mt-1">
                  <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.max(c.share * 100, 2)}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Loans" icon={Landmark}>
          {loans.length === 0 ? (
            <p className="text-sm text-muted">No loans. Ask the assistant what you're eligible for.</p>
          ) : (
            <ul className="space-y-2">
              {loans.map((l) => (
                <li key={l.id} className="rounded-xl border border-line px-3 py-2 text-sm">
                  <div className="flex justify-between">
                    <span className="font-medium">{l.type.toLowerCase()} loan</span>
                    <span className="text-xs text-muted">{l.status}</span>
                  </div>
                  <div className="flex justify-between text-xs text-muted mt-0.5">
                    <span>Outstanding {formatINR(l.outstanding)}</span>
                    <span>EMI {formatINR(l.emi)} · {l.interest_rate}%</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Live transactions" icon={Activity}
        action={<span className="flex items-center gap-1.5 text-xs text-muted"><span className="size-2 rounded-full bg-emerald-500 animate-pulse" />real-time</span>}>
        <ul className="divide-y divide-line -my-2">
          {transactions.map((t) => (
            <li key={t.id} className={`py-2.5 flex items-center gap-3 ${freshIds.has(t.id) ? 'animate-flash' : ''}`}>
              <div className={`grid place-items-center size-9 rounded-full shrink-0 ${t.risk_level === 'HIGH' ? 'bg-red-50 text-red-600' : 'bg-slate-100 text-slate-500'}`}>
                {t.risk_level === 'HIGH' ? <Siren size={16} /> : <Zap size={16} />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{t.merchant}</p>
                <p className="text-xs text-muted truncate">
                  {formatTime(t.timestamp)} · {t.category} · {t.channel} · {t.city}{t.country !== 'IN' ? `, ${t.country}` : ''}
                </p>
              </div>
              <div className="text-right shrink-0">
                <p className={`text-sm font-semibold tabular-nums ${t.direction === 'CREDIT' ? 'text-emerald-600' : ''} ${t.status === 'DECLINED' ? 'line-through text-muted' : ''}`}>
                  {t.direction === 'CREDIT' ? '+' : '−'}{formatINR(t.amount)}
                </p>
                <div className="flex justify-end gap-1 mt-0.5">
                  {t.status === 'DECLINED' ? (
                    <span className="text-[11px] font-medium text-slate-500">DECLINED</span>
                  ) : t.risk_level !== 'LOW' && <RiskBadge level={t.risk_level} score={t.risk_score} />}
                </div>
              </div>
              {t.risk_level !== 'LOW' && t.status !== 'DECLINED' && (
                <button title="Ask the assistant about this transaction"
                  onClick={() => onAsk(`I don't recognise the ${formatINR(t.amount)} transaction at ${t.merchant} in ${t.city} on ${formatTime(t.timestamp)}. Is it fraud?`)}
                  className="shrink-0 rounded-lg border border-line p-1.5 text-muted hover:text-brand-700 hover:border-brand-500">
                  <MessageSquare size={14} />
                </button>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Demo controls" icon={FlaskConical}>
        <p className="text-xs text-muted mb-3">
          Live transactions also arrive automatically every few seconds. Use these buttons to trigger scenarios on demand.
        </p>
        <div className="flex flex-wrap gap-2">
          <DemoButton onClick={() => onSimulate(false)} disabled={busy} icon={Zap}>Normal transaction</DemoButton>
          <DemoButton onClick={() => onSimulate(true)} disabled={busy} icon={Siren} danger>Suspicious transaction</DemoButton>
          <DemoButton onClick={onResetCards} disabled={busy} icon={RotateCcw}>Re-activate cards</DemoButton>
        </div>
      </Card>
    </div>
  )
}

function Stat({ label, value, warn }) {
  return (
    <div className="rounded-xl bg-white/10 px-3 py-2">
      <p className="text-[11px] text-brand-100/70">{label}</p>
      <p className={`font-semibold tabular-nums truncate ${warn ? 'text-amber-300' : ''}`}>{value}</p>
    </div>
  )
}

function DemoButton({ children, icon: Icon, danger, ...props }) {
  return (
    <button {...props}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${danger ? 'border-red-200 text-red-700 hover:bg-red-50' : 'border-line hover:bg-slate-50'}`}>
      <Icon size={14} /> {children}
    </button>
  )
}
