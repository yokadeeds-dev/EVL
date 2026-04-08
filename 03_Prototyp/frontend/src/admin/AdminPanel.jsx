import { useState, useEffect, useRef } from 'react'

const API_BASE = '/api'

function StatusDot({ ok }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full mr-2 ${ok ? 'bg-green-500' : 'bg-red-400'}`}
    />
  )
}

function DocRow({ doc, onDelete }) {
  const [confirming, setConfirming] = useState(false)
  const icons = { '.pdf': '📄', '.md': '📝', '.txt': '📃', '.docx': '📋' }

  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-base">{icons[doc.suffix] || '📄'}</span>
        <span className="text-sm text-gray-800 truncate">{doc.name}</span>
        <span className="text-xs text-gray-400 shrink-0">{doc.size_kb} KB</span>
      </div>
      {confirming ? (
        <div className="flex gap-2 shrink-0">
          <button
            onClick={() => { onDelete(doc.name); setConfirming(false) }}
            className="text-xs px-2 py-1 bg-red-50 text-red-600 border border-red-200 rounded hover:bg-red-100"
          >
            Löschen
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="text-xs px-2 py-1 border border-gray-200 rounded hover:bg-gray-50"
          >
            Abbruch
          </button>
        </div>
      ) : (
        <button
          onClick={() => setConfirming(true)}
          className="text-xs text-gray-400 hover:text-red-500 shrink-0 ml-4"
        >
          ✕
        </button>
      )}
    </div>
  )
}

export default function AdminPanel({ adminKey, onLogout }) {
  const [kbStatus, setKbStatus] = useState(null)
  const [documents, setDocuments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [message, setMessage] = useState(null)
  const fileRef = useRef()

  // Fix: JWT Bearer Token statt X-API-Key
  const headers = { 'Authorization': `Bearer ${adminKey}` }

  const flash = (text, type = 'ok') => {
    setMessage({ text, type })
    setTimeout(() => setMessage(null), 4000)
  }

  const loadStatus = async () => {
    try {
      const [s, d] = await Promise.all([
        fetch(`${API_BASE}/admin/kb-status`, { headers }).then(r => r.json()),
        fetch(`${API_BASE}/admin/documents`, { headers }).then(r => r.json()),
      ])
      setKbStatus(s)
      setDocuments(d.documents || [])
    } catch {
      flash('Verbindung zum Backend fehlgeschlagen.', 'error')
    }
  }

  useEffect(() => { loadStatus() }, [])

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files)
    if (!files.length) return
    setUploading(true)
    let ok = 0, fail = 0
    for (const file of files) {
      const fd = new FormData()
      fd.append('file', file)
      const r = await fetch(`${API_BASE}/admin/upload`, { method: 'POST', headers, body: fd })
      r.ok ? ok++ : fail++
    }
    setUploading(false)
    flash(
      fail === 0
        ? `${ok} Datei(en) hochgeladen.`
        : `${ok} OK, ${fail} fehlgeschlagen.`,
      fail === 0 ? 'ok' : 'error'
    )
    await loadStatus()
    fileRef.current.value = ''
  }

  const handleIngest = async () => {
    setIngesting(true)
    const r = await fetch(`${API_BASE}/admin/ingest`, {
      method: 'POST',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: './knowledge_base' }),
    })
    setIngesting(false)
    const data = await r.json()
    r.ok
      ? flash(`Eingelesen: ${data.documents_ingested} Dokument(e).`)
      : flash(data.detail || 'Fehler beim Einlesen.', 'error')
    await loadStatus()
  }

  const handleDelete = async (filename) => {
    await fetch(`${API_BASE}/admin/documents/${encodeURIComponent(filename)}`, {
      method: 'DELETE', headers,
    })
    await loadStatus()
  }

  const handleReset = async () => {
    setResetting(true)
    const r = await fetch(`${API_BASE}/admin/kb-reset`, { method: 'DELETE', headers })
    setResetting(false)
    setConfirmReset(false)
    r.ok ? flash('Wissensbasis geleert.') : flash('Reset fehlgeschlagen.', 'error')
    await loadStatus()
  }

  return (
    <div className="max-w-2xl mx-auto py-10 px-4">

      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-1">
          <div className="text-xs text-gray-400 font-mono">EVL-2026-002 · Admin</div>
          {onLogout && (
            <button
              onClick={onLogout}
              className="text-xs text-gray-400 hover:text-gray-700 border border-gray-200 rounded px-2 py-1"
            >
              ← Zurück zur App
            </button>
          )}
        </div>
        <h1 className="text-2xl font-semibold text-gray-900">Wissensbasis verwalten</h1>
      </div>

      {/* Status */}
      {kbStatus && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">Status</div>
          <div className="flex items-center gap-6">
            <div>
              <div className="flex items-center text-sm">
                <StatusDot ok={!kbStatus.is_empty} />
                {kbStatus.is_empty ? 'Wissensbasis leer' : 'Wissensbasis aktiv'}
              </div>
            </div>
            <div className="text-sm text-gray-500">
              {kbStatus.document_count} Chunks indexiert
            </div>
            <div className="text-sm text-gray-500">
              {documents.length} Dateien
            </div>
          </div>
        </div>
      )}

      {/* Flash-Meldung */}
      {message && (
        <div className={`mb-4 px-4 py-2.5 rounded-lg text-sm ${
          message.type === 'error'
            ? 'bg-red-50 text-red-700 border border-red-200'
            : 'bg-green-50 text-green-700 border border-green-200'
        }`}>
          {message.text}
        </div>
      )}

      {/* Upload */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
        <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">
          Dokumente hochladen
        </div>
        <p className="text-xs text-gray-500 mb-3">
          Erlaubt: .pdf, .txt, .md, .docx · Max. 10 MB pro Datei
        </p>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".pdf,.txt,.md,.docx"
          onChange={handleUpload}
          disabled={uploading}
          className="block w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border file:border-gray-300 file:text-sm file:bg-gray-50 file:cursor-pointer hover:file:bg-gray-100"
        />
        {uploading && <p className="text-xs text-gray-400 mt-2">Lade hoch…</p>}
      </div>

      {/* Dokumente */}
      {documents.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">
            Dateien in Wissensbasis ({documents.length})
          </div>
          {documents.map(doc => (
            <DocRow key={doc.name} doc={doc} onDelete={handleDelete} />
          ))}
        </div>
      )}

      {/* Aktionen */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
        <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">Aktionen</div>
        <div className="flex gap-3 flex-wrap">
          <button
            onClick={handleIngest}
            disabled={ingesting || documents.length === 0}
            className="text-sm px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-700 disabled:opacity-40"
          >
            {ingesting ? 'Indexiere…' : 'In Vektordatenbank einlesen'}
          </button>
          <button
            onClick={() => setConfirmReset(true)}
            disabled={resetting || kbStatus?.is_empty}
            className="text-sm px-4 py-2 border border-red-200 text-red-600 rounded-lg hover:bg-red-50 disabled:opacity-40"
          >
            Vektordatenbank leeren
          </button>
        </div>
        {confirmReset && (
          <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            Alle indizierten Daten werden gelöscht. Dateien bleiben erhalten.
            <div className="flex gap-2 mt-2">
              <button onClick={handleReset} className="px-3 py-1 bg-red-600 text-white rounded text-xs hover:bg-red-700">
                Ja, leeren
              </button>
              <button onClick={() => setConfirmReset(false)} className="px-3 py-1 border border-red-300 rounded text-xs hover:bg-red-100">
                Abbruch
              </button>
            </div>
          </div>
        )}
      </div>

      <p className="text-xs text-gray-400 text-center">
        Nach dem Hochladen immer „In Vektordatenbank einlesen" ausführen.
      </p>
    </div>
  )
}
