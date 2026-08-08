import type { ApiError, Detection, FormatMap } from './types'

export async function getFormats(): Promise<FormatMap> {
  const response = await fetch('/api/formats')
  if (!response.ok) {
    throw new Error('Could not reach the converter backend.')
  }
  return response.json()
}

/**
 * Ask the backend whether the file's bytes match its extension. Advisory: a failure
 * here is swallowed by the caller rather than blocking the conversion.
 */
export async function detect(file: File): Promise<Detection> {
  const body = new FormData()
  body.append('file', file)

  const response = await fetch('/api/detect', { method: 'POST', body })
  if (!response.ok) {
    throw new Error('Could not inspect the file.')
  }
  return response.json()
}

export interface Converted {
  blob: Blob
  filename: string
}

export async function convert(file: File, targetId: string): Promise<Converted> {
  const body = new FormData()
  body.append('file', file)
  body.append('target', targetId)

  const response = await fetch('/api/convert', { method: 'POST', body })

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Conversion failed'))
  }

  return {
    blob: await response.blob(),
    filename: filenameFrom(response.headers.get('Content-Disposition')),
  }
}

/**
 * Combine several files of one format into one. Order matters: the files are merged
 * in the order given, which is the order the user added them.
 */
export async function combine(files: File[]): Promise<Converted> {
  const body = new FormData()
  for (const file of files) {
    body.append('files', file)
  }

  const response = await fetch('/api/combine', { method: 'POST', body })
  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Combining failed'))
  }

  return {
    blob: await response.blob(),
    filename: filenameFrom(response.headers.get('Content-Disposition')),
  }
}

/** Unpack the backend's {error, hint} failure body into one message. */
async function errorMessage(response: Response, fallback: string): Promise<string> {
  let message = `${fallback} (${response.status}).`
  let hint: string | null | undefined
  try {
    const payload: ApiError = await response.json()
    message = payload.error ?? message
    hint = payload.hint
  } catch {
    // Non-JSON error body, keep the generic message.
  }
  return hint ? `${message}\n\n${hint}` : message
}

/** Pull the download name out of `attachment; filename="report.pdf"`. */
function filenameFrom(disposition: string | null): string {
  const match = disposition?.match(/filename="(.+?)"/)
  return match ? match[1] : 'converted'
}

/** Extension of a filename, lowercased and including the dot. "" if there is none. */
export function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot === -1 ? '' : filename.slice(dot).toLowerCase()
}
