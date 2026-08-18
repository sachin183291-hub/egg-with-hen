import React, { useState, useRef, useEffect } from 'react'
import { aiApi } from '../services/api'
import {
  Send,
  Paperclip,
  X,
  Loader,
  Bot,
  User as UserIcon,
  Image as ImageIcon,
  Camera,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface TrayTypes {
  green_plastic: number
  paper_cardboard: number
  other: number
  unknown: number
}

interface AnalysisData {
  success: boolean
  egg_count: number
  tray_count: number
  tray_types: TrayTypes
  confidence: 'high' | 'medium' | 'low'
  image_quality: 'good' | 'fair' | 'poor'
  notes: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  imagePreview?: string   // blob URL for user messages
  analysis?: AnalysisData // structured result from assistant
  loading?: boolean
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const confidenceColor = (c: string) => {
  if (c === 'high') return '#10b981'
  if (c === 'medium') return '#f59e0b'
  return '#ef4444'
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

const uid = () => Math.random().toString(36).slice(2)

// ─── Component ────────────────────────────────────────────────────────────────

export default function EggAIChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid(),
      role: 'assistant',
      text:
        '👋 Hello! I\'m your AI Egg & Tray Vision Assistant.\n\nUpload a photo of your egg trays and ask me anything:\n• "How many trays are there?"\n• "How many eggs can you count?"\n• "What type of trays are these?"\n• "How many green plastic trays?"\n\nAttach an image using the 📎 button, then type your question.',
    },
  ])

  // The currently attached image — persists across messages in the same session
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const [attachedPreview, setAttachedPreview] = useState<string | null>(null)
  // The last image sent — re-used for follow-up questions
  const [sessionImageFile, setSessionImageFile] = useState<File | null>(null)

  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleAttach = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setAttachedFile(file)
    setAttachedPreview(URL.createObjectURL(file))
    // Reset the input so the same file can be re-selected
    e.target.value = ''
  }

  const removeAttachment = () => {
    setAttachedFile(null)
    setAttachedPreview(null)
  }

  const clearSession = () => {
    setSessionImageFile(null)
    setAttachedFile(null)
    setAttachedPreview(null)
    setMessages([
      {
        id: uid(),
        role: 'assistant',
        text: '🔄 Session cleared. Upload a new image to start a fresh analysis.',
      },
    ])
  }

  const handleSend = async () => {
    const text = inputText.trim()
    if (!text && !attachedFile) return

    // Determine which image to use: newly attached > session image > none
    const imageToSend = attachedFile || sessionImageFile

    // Build user message
    const userMsg: ChatMessage = {
      id: uid(),
      role: 'user',
      text: text || '(image attached)',
      imagePreview: attachedPreview || undefined,
    }

    // Placeholder for assistant reply
    const loadingMsg: ChatMessage = {
      id: uid(),
      role: 'assistant',
      text: '',
      loading: true,
    }

    setMessages((prev) => [...prev, userMsg, loadingMsg])
    setInputText('')
    setSending(true)

    // Save image to session state
    if (attachedFile) {
      setSessionImageFile(attachedFile)
    }
    setAttachedFile(null)
    setAttachedPreview(null)

    try {
      const formData = new FormData()
      formData.append('message', text || 'Please analyze this image.')
      if (imageToSend) {
        formData.append('image', imageToSend)
      }

      const response = await aiApi.chatAnalyze(formData)
      const { reply, analysis } = response.data

      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsg.id
            ? { ...m, text: reply, analysis: analysis || undefined, loading: false }
            : m
        )
      )
    } catch (err: any) {
      const detail =
        err.response?.data?.detail ||
        'Unable to process your request. Please try again.'

      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsg.id
            ? {
                ...m,
                text: `❌ ${detail}`,
                loading: false,
              }
            : m
        )
      )
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="page-container page-with-bg" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 80px)' }}>
      {/* ─── Header ──────────────────────────────────────────────────── */}
      <header className="page-header" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1 }}>
          <div className="page-icon-wrapper" style={{ background: 'var(--brand-500)' }}>
            <Bot size={20} color="white" />
          </div>
          <div>
            <h1 className="page-title">AI Vision Chat</h1>
            <p className="page-subtitle">
              Ask questions about your egg tray photo — count, type, quality.
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {sessionImageFile && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 10px',
                background: 'rgba(59,130,246,0.12)',
                borderRadius: 6,
                fontSize: '0.78rem',
                color: 'var(--brand-400)',
                border: '1px solid rgba(59,130,246,0.25)',
              }}
            >
              <ImageIcon size={12} />
              Image loaded in session
            </div>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={clearSession}
            title="Clear session and start over"
          >
            Clear Session
          </button>
        </div>
      </header>

      {/* ─── Chat Messages ───────────────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '8px 0 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
            }}
          >
            {/* Avatar */}
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: '50%',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background:
                  msg.role === 'assistant'
                    ? 'linear-gradient(135deg, var(--brand-500), var(--brand-700))'
                    : 'var(--bg-elevated)',
                border: msg.role === 'user' ? '1px solid var(--border-subtle)' : 'none',
              }}
            >
              {msg.role === 'assistant' ? (
                <Bot size={18} color="white" />
              ) : (
                <UserIcon size={18} color="var(--text-secondary)" />
              )}
            </div>

            {/* Bubble */}
            <div
              style={{
                maxWidth: '75%',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
                alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              {/* User image attachment preview */}
              {msg.imagePreview && (
                <img
                  src={msg.imagePreview}
                  alt="Attached"
                  style={{
                    maxWidth: 200,
                    maxHeight: 160,
                    objectFit: 'cover',
                    borderRadius: 10,
                    border: '1px solid var(--border-subtle)',
                  }}
                />
              )}

              {/* Message text bubble */}
              <div
                style={{
                  padding: '10px 14px',
                  borderRadius:
                    msg.role === 'user'
                      ? '16px 16px 4px 16px'
                      : '16px 16px 16px 4px',
                  background:
                    msg.role === 'user'
                      ? 'var(--brand-500)'
                      : 'var(--bg-elevated)',
                  color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
                  border:
                    msg.role === 'assistant'
                      ? '1px solid var(--border-subtle)'
                      : 'none',
                  fontSize: '0.9rem',
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  minWidth: 60,
                }}
              >
                {msg.loading ? (
                  <span
                    style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}
                  >
                    <Loader size={14} className="spinner" />
                    Analyzing…
                  </span>
                ) : (
                  msg.text
                )}
              </div>

              {/* Structured analysis panel (assistant only) */}
              {msg.analysis && !msg.loading && (
                <div
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 12,
                    padding: 14,
                    width: '100%',
                    maxWidth: 340,
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: 'var(--text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.6px',
                      marginBottom: 10,
                    }}
                  >
                    AI Analysis Result
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
                    <div
                      style={{
                        background: 'rgba(245,158,11,0.1)',
                        border: '1px solid rgba(245,158,11,0.3)',
                        borderRadius: 8,
                        padding: '10px 8px',
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontSize: '1.2rem' }}>🥚</div>
                      <div style={{ fontSize: '0.7rem', color: '#f59e0b', fontWeight: 600, marginBottom: 2 }}>
                        EGGS
                      </div>
                      <div style={{ fontSize: '1.6rem', fontWeight: 'bold', color: 'var(--text-primary)', lineHeight: 1 }}>
                        {msg.analysis.egg_count}
                      </div>
                    </div>
                    <div
                      style={{
                        background: 'rgba(59,130,246,0.1)',
                        border: '1px solid rgba(59,130,246,0.3)',
                        borderRadius: 8,
                        padding: '10px 8px',
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontSize: '1.2rem' }}>🟢</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--brand-400)', fontWeight: 600, marginBottom: 2 }}>
                        TRAYS
                      </div>
                      <div style={{ fontSize: '1.6rem', fontWeight: 'bold', color: 'var(--text-primary)', lineHeight: 1 }}>
                        {msg.analysis.tray_count}
                      </div>
                    </div>
                  </div>

                  {/* Tray types */}
                  {msg.analysis.tray_count > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      {[
                        { label: '🟢 Green Plastic', key: 'green_plastic' },
                        { label: '📦 Paper/Cardboard', key: 'paper_cardboard' },
                        { label: '🔵 Other', key: 'other' },
                        { label: '❓ Unknown', key: 'unknown' },
                      ].map(({ label, key }) => {
                        const count = msg.analysis!.tray_types[key as keyof TrayTypes]
                        if (count === 0) return null
                        return (
                          <div
                            key={key}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              fontSize: '0.8rem',
                              padding: '3px 0',
                              color: 'var(--text-secondary)',
                            }}
                          >
                            <span>{label}</span>
                            <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{count}</span>
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {/* Confidence badge */}
                  <span
                    style={{
                      background: `${confidenceColor(msg.analysis.confidence)}20`,
                      color: confidenceColor(msg.analysis.confidence),
                      border: `1px solid ${confidenceColor(msg.analysis.confidence)}40`,
                      borderRadius: 5,
                      padding: '3px 8px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                    }}
                  >
                    Confidence: {cap(msg.analysis.confidence)}
                  </span>

                  {/* Notes */}
                  {msg.analysis.notes && (
                    <div
                      style={{
                        marginTop: 8,
                        fontSize: '0.78rem',
                        color: 'var(--text-muted)',
                        lineHeight: 1.5,
                        borderLeft: '2px solid var(--brand-500)',
                        paddingLeft: 8,
                      }}
                    >
                      {msg.analysis.notes}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* ─── Input area ──────────────────────────────────────────────── */}
      <div
        style={{
          flexShrink: 0,
          borderTop: '1px solid var(--border-subtle)',
          paddingTop: 16,
        }}
      >
        {/* Image attachment preview */}
        {attachedPreview && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 10,
              padding: '6px 10px',
              background: 'var(--bg-elevated)',
              borderRadius: 8,
              border: '1px solid var(--border-subtle)',
              width: 'fit-content',
            }}
          >
            <img
              src={attachedPreview}
              alt="Attachment preview"
              style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 6 }}
            />
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              {attachedFile?.name}
            </span>
            <button
              onClick={removeAttachment}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
              }}
              title="Remove attachment"
            >
              <X size={15} />
            </button>
          </div>
        )}

        {/* Session image indicator */}
        {!attachedFile && sessionImageFile && (
          <div
            style={{
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              marginBottom: 8,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <ImageIcon size={12} />
            Using session image: {sessionImageFile.name} — attach a new photo to replace it.
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          {/* Gallery attach */}
          <button
            id="chat-attach-gallery"
            className="btn btn-secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={sending}
            title="Upload from gallery"
            style={{ padding: '10px 12px', flexShrink: 0 }}
          >
            <Paperclip size={16} />
          </button>

          {/* Camera capture */}
          <button
            id="chat-attach-camera"
            className="btn btn-secondary"
            onClick={() => cameraInputRef.current?.click()}
            disabled={sending}
            title="Capture with camera"
            style={{ padding: '10px 12px', flexShrink: 0 }}
          >
            <Camera size={16} />
          </button>

          {/* Hidden file inputs */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/jpg,image/png,image/webp"
            onChange={handleAttach}
            style={{ display: 'none' }}
          />
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleAttach}
            style={{ display: 'none' }}
          />

          {/* Text input */}
          <textarea
            ref={textareaRef}
            id="chat-message-input"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              sessionImageFile || attachedFile
                ? 'Ask about the image… (Enter to send)'
                : 'Attach an image, then ask a question… (Enter to send)'
            }
            disabled={sending}
            rows={1}
            style={{
              flex: 1,
              resize: 'none',
              borderRadius: 10,
              border: '1px solid var(--border-color)',
              background: 'var(--bg-elevated)',
              color: 'var(--text-primary)',
              padding: '10px 14px',
              fontSize: '0.9rem',
              outline: 'none',
              lineHeight: 1.5,
              minHeight: 42,
              maxHeight: 120,
              overflowY: 'auto',
            }}
          />

          {/* Send button */}
          <button
            id="chat-send-button"
            className="btn btn-primary"
            onClick={handleSend}
            disabled={sending || (!inputText.trim() && !attachedFile)}
            style={{ padding: '10px 16px', flexShrink: 0 }}
            title="Send message"
          >
            {sending ? <Loader size={16} className="spinner" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  )
}
