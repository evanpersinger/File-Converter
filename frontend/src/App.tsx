import { useEffect, useState } from 'react'
import { convert, extensionOf, getFormats } from './api'
import type { FormatMap } from './types'
import './App.css'

type Status =
  | { kind: 'idle' }
  | { kind: 'converting' }
  | { kind: 'error'; message: string }

interface Result {
  url: string
  filename: string
}

export default function App() {
  const [formats, setFormats] = useState<FormatMap | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [target, setTarget] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [result, setResult] = useState<Result | null>(null)

  useEffect(() => {
    getFormats().then(setFormats).catch((e: Error) => setLoadError(e.message))
  }, [])

  // Release the blob URL when it gets replaced or the page unmounts. Without this,
  // every conversion would leak its result until a full page reload.
  useEffect(() => {
    if (!result) return
    return () => URL.revokeObjectURL(result.url)
  }, [result])

  const ext = file ? extensionOf(file.name) : ''
  const targets = (ext && formats?.byExtension[ext]) || []
  const blocked = (ext && formats?.unavailable[ext]) || []

  // Which conversion owns a format button. Registry order decides: pdf->md is
  // registered before pdf->md-ai, and img->txt before img->txt-tables, so the first
  // match is always the free local route and anything after it is an opt-in variant.
  const routesFor = (formatExt: string) => targets.filter((t) => t.ext === formatExt)

  const selected = targets.find((t) => t.id === target) ?? null
  const variants = selected ? routesFor(selected.ext).slice(1) : []

  // What the two summary boxes show. The source comes straight off the filename;
  // the target borrows the registry's display name so both boxes read the same way.
  const sourceName = ext ? ext.slice(1).toUpperCase() : null
  const targetName = formats?.allFormats.find((f) => f.ext === selected?.ext)?.name ?? null

  function pickFile(picked: File | null) {
    setFile(picked)
    setTarget(null)
    setStatus({ kind: 'idle' })
    setResult(null)
  }

  async function runConversion() {
    if (!file || !target) return
    setStatus({ kind: 'converting' })
    setResult(null)
    try {
      const { blob, filename } = await convert(file, target)
      // Hold the result and let the user click Download, rather than firing the
      // download automatically.
      setResult({ url: URL.createObjectURL(blob), filename })
      setStatus({ kind: 'idle' })
    } catch (e) {
      setStatus({ kind: 'error', message: (e as Error).message })
    }
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h2>Convert to</h2>

        <div className="formats">
          {formats?.allFormats.map((f) => {
            const primary = routesFor(f.ext)[0]
            const dep = blocked.find((u) => u.ext === f.ext)
            // Every disabled button says why on hover, so a greyed-out list is never
            // just a dead end.
            const why = primary
              ? undefined
              : !file
                ? 'Choose a file first'
                : dep
                  ? dep.hint
                    ? `${dep.reason}. ${dep.hint}`
                    : dep.reason
                  : `Cannot convert ${ext || 'this file'} to ${f.name}.`

            return (
              <button
                key={f.ext}
                type="button"
                className={selected?.ext === f.ext ? 'format selected' : 'format'}
                disabled={!primary}
                title={why}
                onClick={() => primary && setTarget(primary.id)}
              >
                {f.name}
              </button>
            )
          })}
        </div>

        {file && targets.length === 0 && (
          <p className="muted">Nothing can convert {ext || 'this file'} yet.</p>
        )}

        {variants.map((v) => (
          <label key={v.id} className="option">
            <input
              type="checkbox"
              checked={target === v.id}
              onChange={(e) => setTarget(e.target.checked ? v.id : routesFor(v.ext)[0].id)}
            />
            <span>
              {v.label}
              {v.note && <em className="note">{v.note}</em>}
            </span>
          </label>
        ))}

        {selected?.note && <p className="muted note">{selected.note}</p>}
      </aside>

      <main>
        <h1>File Converter</h1>

        {loadError && <p className="error">{loadError}</p>}

        <label className="filepicker">
          <input type="file" onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />
          <span title={file?.name}>{file ? file.name : 'Choose a file'}</span>
        </label>

        <div className="transfer">
          <div className="slot">
            <div className={sourceName ? 'box filled' : 'box'}>
              <span className="box-value">{sourceName ?? '--'}</span>
            </div>
            <span className="box-label">From</span>
          </div>
          <div className="slot">
            <div className={targetName ? 'box filled' : 'box'}>
              <span className="box-value">{targetName ?? '--'}</span>
            </div>
            <span className="box-label">To</span>
          </div>
        </div>

        <button
          className="convert"
          onClick={runConversion}
          disabled={!target || status.kind === 'converting'}
        >
          {status.kind === 'converting' ? 'Converting...' : 'Convert'}
        </button>

        {result && (
          <a className="download" href={result.url} download={result.filename}>
            Download {result.filename}
          </a>
        )}

        {status.kind === 'error' && <pre className="error">{status.message}</pre>}
      </main>
    </div>
  )
}
