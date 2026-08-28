// Geteilte Typen für das EVL-Frontend.
// Spiegeln die Pydantic-Schemas des Backends (03_Prototyp/backend/main.py).

export type TextType = 'seo' | 'produkt' | 'faq' | 'leicht' | 'social'

export type MandantId = string

// Antwort von GET /me — ACL-Kontext des eingeloggten Users.
export interface UserContext {
  user_id: string
  name: string
  allowed_mandate: MandantId[]
  effective_allowed: MandantId[]
  chinese_wall_pairs: [MandantId, MandantId][]
}

// Antwort von POST /auth/token.
export interface TokenResponse {
  access_token: string
  token_type: string
}

// Antwort von POST /generate.
export interface GenerateResponse {
  result: string
  text_type: TextType
  label: string
  context_chunks_used: number
  rag_active: boolean
}

// Angezeigtes Ergebnis inkl. gewähltem Mandat (für die § 203-Warnung).
export interface GenerateResult extends GenerateResponse {
  mandant: MandantId
}

// Antwort von GET /admin/kb-status.
export interface KBStatus {
  document_count: number
  is_empty: boolean
}

// Ein Dokument aus GET /admin/documents.
export interface DocMeta {
  name: string
  suffix: string
  size_kb: number
}

export type FlashType = 'ok' | 'error'

export interface FlashMessage {
  text: string
  type: FlashType
}

// Fehlerkörper der FastAPI-Endpunkte ({ "detail": ... }).
export interface ApiError {
  detail?: string
}
