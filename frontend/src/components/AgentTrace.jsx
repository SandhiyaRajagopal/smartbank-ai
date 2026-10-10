import { Bot, CircleCheck, CircleX, GitBranch, LoaderCircle, ShieldAlert, ShieldCheck, Sparkles, Workflow, Wrench } from 'lucide-react'
import { AGENT_STYLES, AgentChip } from './ui'

/**
 * Visualises what happened inside the LangGraph workflow for one chat turn:
 * guardrails -> supervisor routing -> each agent's tool calls -> approval -> aggregation.
 */
export default function AgentTrace({ steps, running }) {
  return (
    <div className="flex flex-col h-full min-h-0 rounded-2xl border border-line bg-white">
      <header className="flex items-center gap-2 px-4 py-3 border-b border-line">
        <Workflow size={16} className="text-brand-700" />
        <h2 className="text-sm font-semibold">Agent trace</h2>
        {running && <LoaderCircle size={14} className="animate-spin text-muted ml-auto" />}
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto p-4">
        {!steps?.length ? (
          <div className="text-sm text-muted space-y-3">
            <p>Send a message to watch the multi-agent workflow run step by step.</p>
            <ol className="space-y-1.5 text-xs">
              <li>1. <b>Guardrails</b> mask personal data and block prompt injection</li>
              <li>2. <b>Supervisor</b> (Gemini) classifies intent and picks agents</li>
              <li>3. <b>Specialist agents</b> call banking tools for real data</li>
              <li>4. <b>Approval</b> pauses for your confirmation on risky actions</li>
              <li>5. <b>Aggregator</b> composes one final answer</li>
            </ol>
          </div>
        ) : (
          <ol className="relative border-l border-line ml-2 space-y-4">
            {steps.map((s, i) => <Step key={i} step={s} />)}
          </ol>
        )}
      </div>
    </div>
  )
}

function Step({ step }) {
  const ms = step.ms != null && <span className="text-[10px] text-muted tabular-nums ml-auto">{step.ms} ms</span>
  const row = (icon, color, title, body) => (
    <li className="ml-4">
      <span className={`absolute -left-[11px] grid place-items-center size-[21px] rounded-full ring-4 ring-white ${color}`}>{icon}</span>
      <div className="flex items-center gap-2 text-xs font-semibold">{title}{ms}</div>
      {body && <div className="mt-1 text-xs text-slate-600 space-y-1">{body}</div>}
    </li>
  )

  switch (step.step) {
    case 'guardrail':
      return step.allowed
        ? row(<ShieldCheck size={12} />, 'bg-emerald-100 text-emerald-700', 'Guardrails passed',
            step.pii_masked?.length ? <p>Masked before the LLM: {step.pii_masked.join(', ')}</p> : null)
        : row(<ShieldAlert size={12} />, 'bg-red-100 text-red-700', 'Blocked by guardrails', <p>Reason: {step.reason}</p>)

    case 'supervisor':
      return row(<GitBranch size={12} />, 'bg-brand-100 text-brand-700', 'Supervisor routed request', (
        <>
          <p className="font-mono text-[11px]">intent: {step.intent}{step.fallback ? ' (keyword fallback)' : ''}</p>
          <div className="flex flex-wrap gap-1">
            {step.route.length ? step.route.map((a, i) => <AgentChip key={i} agent={a} />) : <span className="italic">answered directly</span>}
          </div>
          <p className="italic">{step.reasoning}</p>
        </>
      ))

    case 'tool': {
      const color = AGENT_STYLES[step.agent]?.dot || 'bg-slate-400'
      return row(<Wrench size={11} />, 'bg-slate-100 text-slate-600', (
        <span className="flex items-center gap-1.5 font-mono font-medium">
          <span className={`size-1.5 rounded-full ${color}`} />{step.tool}
        </span>
      ), (
        <>
          {Object.keys(step.args || {}).length > 0 && (
            <p className="font-mono text-[11px] break-all text-slate-500">{JSON.stringify(step.args)}</p>
          )}
          {step.requires_confirmation
            ? <p className="text-amber-700 font-medium">⏸ sensitive action, waiting for your confirmation</p>
            : (
              <details>
                <summary className="cursor-pointer text-muted hover:text-ink">result</summary>
                <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-[10px] bg-slate-50 rounded p-2 max-h-40 overflow-y-auto">{step.result}</pre>
              </details>
            )}
        </>
      ))
    }

    case 'agent':
      return row(<Bot size={12} />, 'bg-white ring-1 ring-line text-ink',
        <span className="flex items-center gap-1.5">{step.title} finished</span>,
        <p>{step.tools_used.length ? `${step.tools_used.length} tool call(s)` : 'no tools needed'} · task: <span className="italic">{step.task}</span></p>)

    case 'approval':
      return step.approved
        ? row(<CircleCheck size={12} />, 'bg-emerald-100 text-emerald-700', 'Approved by customer', <p>{step.summary}</p>)
        : row(<CircleX size={12} />, 'bg-slate-200 text-slate-600', 'Cancelled by customer', <p>{step.summary}</p>)

    case 'aggregate':
      return row(<Sparkles size={12} />, 'bg-violet-100 text-violet-700', 'Final answer composed',
        <p>{{ passthrough: 'single agent answer passed through', llm_merge: `merged answers from ${step.agents.length} agents`, direct: 'direct reply from supervisor' }[step.mode] || step.mode}</p>)

    default:
      return row(<Sparkles size={12} />, 'bg-slate-100', step.step)
  }
}
