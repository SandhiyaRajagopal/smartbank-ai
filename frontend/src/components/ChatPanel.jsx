import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Bot, LoaderCircle, Plus, Send, ShieldAlert, Sparkles, TriangleAlert, Workflow } from 'lucide-react'

const QUICK_PROMPTS = [
  "What's my account balance?",
  'Where did I spend the most this month?',
  'Is there any suspicious activity on my account?',
  'Am I eligible for a ₹5 lakh personal loan for 3 years?',
  'What documents do I need for KYC?',
  'Check my account for fraud, then tell me if I can get an ₹8 lakh car loan.',
]

export default function ChatPanel({ chat, draft, setDraft, onShowTrace }) {
  const { messages, pending, streaming, send, confirm, newChat, activeTurn, setActiveTurn } = chat
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, pending])
  useEffect(() => { if (draft) inputRef.current?.focus() }, [draft])

  function submit(e) {
    e.preventDefault()
    send(draft)
    setDraft('')
  }

  return (
    <div className="flex flex-col h-full min-h-0 rounded-2xl border border-line bg-white">
      <header className="flex items-center justify-between px-4 py-3 border-b border-line">
        <div className="flex items-center gap-2">
          <span className="grid place-items-center size-8 rounded-lg bg-brand-50 text-brand-700"><Bot size={18} /></span>
          <div>
            <h2 className="text-sm font-semibold leading-tight">SmartBank Assistant</h2>
            <p className="text-[11px] text-muted">Supervisor + 4 specialist agents</p>
          </div>
        </div>
        <button onClick={newChat} className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-xs font-medium hover:bg-slate-50">
          <Plus size={14} /> New chat
        </button>
      </header>

      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center pt-6">
            <Sparkles className="mx-auto text-brand-500" />
            <p className="mt-2 text-sm font-medium">How can I help with your banking today?</p>
            <div className="mt-4 grid gap-2">
              {QUICK_PROMPTS.map((p) => (
                <button key={p} onClick={() => send(p)} disabled={streaming}
                  className="text-left text-sm rounded-xl border border-line px-3 py-2 hover:border-brand-500 hover:bg-brand-50">
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => m.role === 'user' ? (
          <div key={m.id} className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-700 text-white px-3.5 py-2 text-sm whitespace-pre-wrap">{m.content}</div>
          </div>
        ) : (
          <div key={m.id} className="flex gap-2">
            <span className="grid place-items-center size-7 rounded-full bg-brand-50 text-brand-700 shrink-0 mt-0.5"><Bot size={15} /></span>
            <div className={`max-w-[88%] rounded-2xl rounded-tl-md px-3.5 py-2 text-sm ${m.error ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-slate-50 border border-line'}`}>
              {m.loading && !m.content ? (
                <span className="flex items-center gap-2 text-muted"><LoaderCircle size={14} className="animate-spin" /> Agents are working…</span>
              ) : (
                <>
                  {m.error && <TriangleAlert size={14} className="inline mr-1 -mt-0.5" />}
                  <div className="prose-chat"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                  {m.loading && <LoaderCircle size={14} className="animate-spin text-muted mt-1" />}
                </>
              )}
              {chat.traces[m.turn]?.length > 0 && !m.loading && (
                <button onClick={() => { setActiveTurn(m.turn); onShowTrace?.() }}
                  className={`mt-1.5 inline-flex items-center gap-1 text-[11px] ${activeTurn === m.turn ? 'text-brand-700 font-medium' : 'text-muted hover:text-brand-700'}`}>
                  <Workflow size={12} /> agent trace
                </button>
              )}
            </div>
          </div>
        ))}

        {pending && (
          <div className="ml-9 rounded-2xl border-2 border-amber-300 bg-amber-50 p-4 animate-slide-in" role="alertdialog" aria-label="Confirm action">
            <p className="flex items-center gap-2 text-sm font-semibold text-amber-900">
              <ShieldAlert size={16} /> Your confirmation is needed
            </p>
            <p className="text-sm mt-1.5 text-amber-950">{pending.summary}</p>
            <p className="text-[11px] text-amber-800 mt-1">Nothing has been changed yet. This action needs your explicit approval.</p>
            <div className="flex gap-2 mt-3">
              <button onClick={() => confirm(true)} disabled={streaming}
                className="rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium px-4 py-1.5 disabled:opacity-50">Confirm</button>
              <button onClick={() => confirm(false)} disabled={streaming}
                className="rounded-lg border border-amber-300 bg-white text-sm font-medium px-4 py-1.5 hover:bg-amber-100 disabled:opacity-50">Cancel</button>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={submit} className="border-t border-line p-3 flex gap-2">
        <input ref={inputRef} value={draft} onChange={(e) => setDraft(e.target.value)}
          disabled={!!pending} maxLength={2000}
          placeholder={pending ? 'Confirm or cancel the action above first' : 'Ask about balances, fraud, loans, policies…'}
          className="flex-1 min-w-0 rounded-xl border border-line px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-50" />
        <button disabled={streaming || !draft.trim() || !!pending} aria-label="Send"
          className="grid place-items-center rounded-xl bg-brand-700 hover:bg-brand-600 text-white px-3 disabled:opacity-40">
          {streaming ? <LoaderCircle size={18} className="animate-spin" /> : <Send size={18} />}
        </button>
      </form>
    </div>
  )
}
