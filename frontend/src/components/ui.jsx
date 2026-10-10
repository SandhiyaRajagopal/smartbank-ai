// Small shared UI pieces.

export function Card({ title, icon: Icon, action, children, className = '' }) {
  return (
    <section className={`rounded-2xl border border-line bg-white ${className}`}>
      {title && (
        <header className="flex items-center justify-between px-4 pt-4">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            {Icon && <Icon size={16} className="text-brand-700" />} {title}
          </h3>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

const RISK_STYLES = {
  HIGH: 'bg-red-50 text-red-700 ring-red-200',
  MEDIUM: 'bg-amber-50 text-amber-700 ring-amber-200',
  LOW: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
}

export function RiskBadge({ level, score }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${RISK_STYLES[level] || RISK_STYLES.LOW}`}>
      {level}{score ? ` · ${score}` : ''}
    </span>
  )
}

// Colours used for each agent everywhere in the UI (trace panel, chips).
export const AGENT_STYLES = {
  customer: { label: 'Customer Agent', chip: 'bg-sky-50 text-sky-700 ring-sky-200', dot: 'bg-sky-500' },
  fraud: { label: 'Fraud & Risk Agent', chip: 'bg-red-50 text-red-700 ring-red-200', dot: 'bg-red-500' },
  credit: { label: 'Credit & Loan Agent', chip: 'bg-violet-50 text-violet-700 ring-violet-200', dot: 'bg-violet-500' },
  compliance: { label: 'Compliance & Policy Agent', chip: 'bg-amber-50 text-amber-800 ring-amber-200', dot: 'bg-amber-500' },
}

export function AgentChip({ agent }) {
  const s = AGENT_STYLES[agent] || { label: agent, chip: 'bg-slate-50 text-slate-700 ring-slate-200' }
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${s.chip}`}>{s.label}</span>
}
