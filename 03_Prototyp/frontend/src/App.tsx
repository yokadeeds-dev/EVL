import { useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import AdminPanel from './admin/AdminPanel'
import type {
  ApiError,
  GenerateResponse,
  GenerateResult,
  TextType,
  TokenResponse,
  UserContext,
} from './types'

const API_BASE = '/api'

const TEMPLATE_LABELS: Record<TextType, string> = {
  seo: 'SEO-Text',
  produkt: 'Produktbeschreibung',
  faq: 'FAQ-Antwort',
  leicht: 'Leichte Sprache',
  social: 'Social-Media-Post',
}

type BadgeVariant = 'gray' | 'green' | 'blue' | 'red'
type View = 'main' | 'admin-login' | 'admin'

function Badge({ children, variant = 'gray' }: { children: ReactNode; variant?: BadgeVariant }) {
  const colors: Record<BadgeVariant, string> = {
    gray: 'bg-gray-100 text-gray-600',
    green: 'bg-green-100 text-green-700',
    blue: 'bg-blue-100 text-blue-700',
    red: 'bg-red-100 text-red-700',
  }
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${colors[variant]}`}>
      {children}
    </span>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={handleCopy}
      className="text-sm px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 transition-colors"
    >
      {copied ? '✓ Kopiert' : 'Kopieren'}
    </button>
  )
}

export default function App() {
  const [view, setView] = useState<View>('main')
  const [adminKey, setAdminKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [jwtToken, setJwtToken] = useState('')
  const [userContext, setUserContext] = useState<UserContext | null>(null)

  const [textType, setTextType] = useState<TextType>('seo')
  const [topic, setTopic] = useState('')
  const [useRag, setUseRag] = useState(true)
  const [targetMandant, setTargetMandant] = useState('')

  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<GenerateResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [apiReady, setApiReady] = useState<boolean | null>(null)

  // Backend-Status prüfen
  useEffect(() => {
    fetch(`${API_BASE}/status`)
      .then((r) => r.json())
      .then((data: { status: string }) => setApiReady(data.status === 'ok'))
      .catch(() => setApiReady(false))
  }, [])

  // User-Kontext prüfen (ACL)
  useEffect(() => {
    if (!jwtToken) {
      setUserContext(null)
      return
    }
    fetch(`${API_BASE}/me`, { headers: { Authorization: `Bearer ${jwtToken}` } })
      .then((res) => (res.ok ? (res.json() as Promise<UserContext>) : null))
      .then((data) => {
        setUserContext(data)
        if (data && data.effective_allowed) {
          setTargetMandant('')
        }
      })
      .catch(() => setUserContext(null))
  }, [jwtToken])

  const handleLogin = async () => {
    if (!username || !password) return
    setError(null)
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)
    try {
      const r = await fetch(`${API_BASE}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
      })
      if (r.ok) {
        const data = (await r.json()) as TokenResponse
        setJwtToken(data.access_token)
      } else {
        const err = (await r.json()) as ApiError
        setJwtToken('')
        setUserContext(null)
        setError(err.detail || 'Login fehlgeschlagen.')
      }
    } catch {
      setError('Server nicht erreichbar.')
    }
  }

  const handleGenerate = async () => {
    if (!topic.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const payload: {
        text_type: TextType
        topic: string
        use_rag: boolean
        target_mandant?: string
      } = { text_type: textType, topic: topic.trim(), use_rag: useRag }
      if (targetMandant) payload.target_mandant = targetMandant

      const res = await fetch(`${API_BASE}/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${jwtToken}`,
        },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const err = (await res.json()) as ApiError
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const data = (await res.json()) as GenerateResponse
      setResult({ ...data, mandant: targetMandant })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unbekannter Fehler')
    } finally {
      setLoading(false)
    }
  }

  if (view === 'admin' && adminKey)
    return (
      <AdminPanel
        adminKey={adminKey}
        onLogout={() => {
          setView('main')
          setAdminKey('')
        }}
      />
    )

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      {view === 'admin-login' && (
        <AdminLoginModal
          onLogin={(k) => {
            setAdminKey(k)
            setView('admin')
          }}
          onClose={() => setView('main')}
        />
      )}
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400 font-mono">EVL-2026-002</span>
              {apiReady === true && <Badge variant="green">API verbunden</Badge>}
              {apiReady === false && <Badge>API nicht erreichbar</Badge>}
              {userContext && <Badge variant="blue">Eingeloggt als: {userContext.name}</Badge>}
            </div>
            <button
              onClick={() => setView('admin-login')}
              className="text-xs text-gray-400 hover:text-gray-600 border border-gray-200 rounded px-2 py-1"
            >
              Admin
            </button>
          </div>
          <h1 className="text-2xl font-semibold text-gray-900">Content-Assistant</h1>
          <p className="text-sm text-gray-500 mt-1">
            KI-gestützte Textentwürfe auf Basis Ihrer Firmenwissensbasis
          </p>
        </div>

        {/* Hinweis KI-generiert */}
        <div className="mb-6 text-xs text-gray-400 bg-gray-100 rounded px-3 py-2">
          Dieser Assistent erstellt KI-generierte Entwürfe. Alle Texte müssen vor Veröffentlichung
          menschlich geprüft und freigegeben werden.
        </div>

        {/* Formular */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Benutzerkonto (SSO)</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="anwalt_a, anwalt_b, anwalt_c…"
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                placeholder="Passwort"
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={handleLogin}
                className="bg-gray-200 text-gray-700 font-medium px-4 py-2 rounded-lg text-sm hover:bg-gray-300 transition"
              >
                Login
              </button>
            </div>
          </div>

          {userContext && userContext.effective_allowed && (
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Mandats-Fokus (Optional)
              </label>
              <select
                value={targetMandant}
                onChange={(e) => setTargetMandant(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">-- Alle berechtigten Mandate --</option>
                {userContext.effective_allowed.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Texttyp</label>
            <select
              value={textType}
              onChange={(e) => setTextType(e.target.value as TextType)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {(Object.entries(TEMPLATE_LABELS) as [TextType, string][]).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Thema / Stichwörter</label>
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="z. B. Kaufvertrag Vergütungsklauseln"
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="mb-6 flex items-center gap-2">
            <input
              type="checkbox"
              id="use-rag"
              checked={useRag}
              onChange={(e) => setUseRag(e.target.checked)}
              className="rounded border-gray-300"
            />
            <label htmlFor="use-rag" className="text-sm text-gray-600">
              Mandantenwissen einbeziehen (RAG)
            </label>
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading || !topic.trim() || !jwtToken}
            className="w-full bg-gray-900 text-white text-sm font-medium py-2.5 rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Generiere…' : 'Entwurf erstellen'}
          </button>
        </div>

        {/* Fehler */}
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Ergebnis */}
        {result && (
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-800">{result.label}</span>
                {result.rag_active && (
                  <Badge variant="blue">{result.context_chunks_used} Kontext-Chunks</Badge>
                )}
              </div>
              <CopyButton text={result.result} />
            </div>

            {result.rag_active && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-xs font-semibold">
                ⚠️ Vorsicht: Sensible Daten aus{' '}
                {result.mandant ? `Mandat ${result.mandant}` : 'verschiedenen Mandaten'} verwendet.
                Unterliegt § 203 StGB (Anwaltliche Schweigepflicht).
              </div>
            )}

            <pre className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed font-sans mt-2">
              {result.result}
            </pre>
            <p className="mt-4 text-xs text-gray-400">
              Bitte Entwurf inhaltlich prüfen und vor Veröffentlichung freigeben.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

// Admin-Login-Modal-Komponente
export function AdminLoginModal({
  onLogin,
  onClose,
}: {
  onLogin: (token: string) => void
  onClose: () => void
}) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(false)

  const tryLogin = async () => {
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)
    const r1 = await fetch('/api/auth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData,
    })
    if (!r1.ok) {
      setError(true)
      setTimeout(() => setError(false), 2000)
      return
    }

    const data = (await r1.json()) as TokenResponse
    // Admin-Rolle serverseitig prüfen: require_admin gibt 403 für Nicht-Admins.
    const r2 = await fetch('/api/admin/kb-status', {
      headers: { Authorization: `Bearer ${data.access_token}` },
    })
    if (r2.ok) {
      onLogin(data.access_token)
    } else {
      setError(true)
      setTimeout(() => setError(false), 2000)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl border border-gray-200 p-6 w-80">
        <h2 className="text-base font-semibold text-gray-900 mb-1">Admin-Bereich</h2>
        <p className="text-xs text-gray-500 mb-4">Admin-User + Passwort eingeben</p>
        <input
          type="text"
          placeholder="anwalt_a (Admin)"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          type="password"
          placeholder="Passwort"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && tryLogin()}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {error && <p className="text-xs text-red-500 mb-2">Ungültiger Admin oder Passwort.</p>}
        <div className="flex gap-2">
          <button
            onClick={tryLogin}
            className="flex-1 bg-gray-900 text-white text-sm py-2 rounded-lg hover:bg-gray-700"
          >
            Anmelden
          </button>
          <button
            onClick={onClose}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}
