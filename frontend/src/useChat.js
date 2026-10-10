import { useCallback, useEffect, useRef, useState } from 'react'
import { api, streamSSE } from './api'

const newId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random())).replace(/[^a-zA-Z0-9-]/g, '').slice(0, 32)

function loadConversationId(email) {
  try {
    const key = `smartbank_conv_${email}`
    let id = localStorage.getItem(key)
    if (!id) { id = newId(); localStorage.setItem(key, id) }
    return id
  } catch {
    return newId()
  }
}

/**
 * All chat state in one hook: messages, the live agent trace of each turn,
 * the pending confirmation (human-in-the-loop) and the streaming status.
 */
export function useChat(user, onActivity) {
  const [conversationId, setConversationId] = useState(() => loadConversationId(user.email))
  const [messages, setMessages] = useState([])
  const [traces, setTraces] = useState({})        // turnId -> [trace steps]
  const [activeTurn, setActiveTurn] = useState(null)
  const [pending, setPending] = useState(null)    // confirmation payload + turn
  const [streaming, setStreaming] = useState(false)
  const activityRef = useRef(onActivity)
  activityRef.current = onActivity

  // restore the conversation from the server-side checkpointer after a reload
  useEffect(() => {
    api.get(`/api/chat/history?conversation_id=${conversationId}`).then((h) => {
      const turn = 'restored'
      setMessages(h.messages.map((m, i) => ({ ...m, id: `h${i}`, turn })))
      setPending(h.pending_confirmation ? { ...h.pending_confirmation, turn } : null)
    }).catch(() => {})
  }, [conversationId])

  const updateAssistant = (turn, patch) =>
    setMessages((ms) => ms.map((m) => (m.role === 'assistant' && m.turn === turn ? { ...m, ...patch } : m)))

  const handleStream = useCallback(async (path, body, turn) => {
    setStreaming(true)
    try {
      await streamSSE(path, body, (type, data) => {
        if (type === 'trace') setTraces((t) => ({ ...t, [turn]: [...(t[turn] || []), data] }))
        else if (type === 'confirmation') {
          setPending({ ...data, turn })
          updateAssistant(turn, { content: data.message, loading: false })
        } else if (type === 'final') updateAssistant(turn, { content: data.reply, loading: false, error: false })
        else if (type === 'error') updateAssistant(turn, { content: data.message, loading: false, error: true })
      })
    } catch (err) {
      updateAssistant(turn, { content: err.message, loading: false, error: true })
    } finally {
      setStreaming(false)
      activityRef.current?.()
    }
  }, [])

  const send = useCallback((text) => {
    const message = text.trim()
    if (!message || streaming || pending) return
    const turn = newId()
    setActiveTurn(turn)
    setMessages((ms) => [...ms,
      { id: `${turn}-u`, role: 'user', content: message, turn },
      { id: `${turn}-a`, role: 'assistant', content: '', turn, loading: true }])
    handleStream('/api/chat', { message, conversation_id: conversationId }, turn)
  }, [streaming, pending, conversationId, handleStream])

  const confirm = useCallback((approved) => {
    if (!pending) return
    const { turn } = pending
    setPending(null)
    setActiveTurn(turn)
    updateAssistant(turn, { loading: true })
    handleStream('/api/chat/confirm', { conversation_id: conversationId, approved }, turn)
  }, [pending, conversationId, handleStream])

  const newChat = useCallback(() => {
    const id = newId()
    try { localStorage.setItem(`smartbank_conv_${user.email}`, id) } catch { /* ignore */ }
    setConversationId(id)
    setMessages([])
    setTraces({})
    setPending(null)
    setActiveTurn(null)
  }, [user.email])

  return { messages, traces, activeTurn, setActiveTurn, pending, streaming, send, confirm, newChat }
}
