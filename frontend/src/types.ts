/** A conversion the backend can actually perform right now. */
export interface Target {
  id: string
  label: string
  ext: string
  note?: string
}

/** A conversion the backend knows about but cannot run, and why. */
export interface Unavailable {
  id: string
  label: string
  ext: string
  reason: string
  hint?: string
}

/** One output format, rendered as a single button in the grid. */
export interface FormatOption {
  ext: string
  name: string
}

/**
 * The whole format map, keyed by lowercased source extension (".csv", ".pdf").
 * The frontend hardcodes no extensions and no format names, it only indexes this
 * by the uploaded file's extension. Adding a converter is a backend-only change.
 */
export interface FormatMap {
  allFormats: FormatOption[]
  byExtension: Record<string, Target[]>
  unavailable: Record<string, Unavailable[]>
}

export interface ApiError {
  error: string
  hint?: string | null
}
