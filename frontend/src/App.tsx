import { useEffect, useRef, useState } from 'react'
import { combine, convert, detect, extensionOf, getFormats } from './api'
import type { FormatMap, Mismatch } from './types'
import './App.css'

type Status =
  | { kind: 'idle' }
  | { kind: 'converting' }
  | { kind: 'combining' }
  | { kind: 'error'; message: string }

interface Result {
  url: string
  filename: string
}

// Different spellings of one format. Kept in step with SUFFIX_ALIASES in
// combine_files.py, so the button enables exactly when the backend would accept.
const EXT_ALIASES: Record<string, string> = {
  '.jpeg': '.jpg',
  '.tif': '.tiff',
  '.htm': '.html',
}

const canonical = (ext: string) => EXT_ALIASES[ext] ?? ext

export default function App() {
  const [formats, setFormats] = useState<FormatMap | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [target, setTarget] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [result, setResult] = useState<Result | null>(null)
  const [dragging, setDragging] = useState(false)
  const [mismatch, setMismatch] = useState<Mismatch | null>(null)
  // Which file the newest detect() call was for. Adding a second file while the
  // first check is in flight would otherwise let the stale answer win.
  const latestPick = useRef<File | null>(null)

  useEffect(() => {
    getFormats().then(setFormats).catch((e: Error) => setLoadError(e.message))
  }, [])

  // Release the blob URL when it gets replaced or the page unmounts. Without this,
  // every conversion would leak its result until a full page reload.
  useEffect(() => {
    if (!result) return
    return () => URL.revokeObjectURL(result.url)
  }, [result])

  // A file dropped anywhere but the picker makes the browser navigate to it, which
  // throws away whatever is on screen. Swallow drops outside the target.
  useEffect(() => {
    const swallow = (e: DragEvent) => e.preventDefault()
    window.addEventListener('dragover', swallow)
    window.addEventListener('drop', swallow)
    return () => {
      window.removeEventListener('dragover', swallow)
      window.removeEventListener('drop', swallow)
    }
  }, [])

  // The first file drives the format buttons and the mismatch check. Combining
  // requires everything to share one extension anyway, so it is representative.
  const primary = files[0] ?? null
  const ext = primary ? extensionOf(primary.name) : ''
  const targets = (ext && formats?.byExtension[ext]) || []
  const blocked = (ext && formats?.unavailable[ext]) || []

  const distinctExts = [...new Set(files.map((f) => canonical(extensionOf(f.name))))]
  const mixedExtensions = files.length >= 2 && distinctExts.length > 1
  const canCombine = files.length >= 2 && !mixedExtensions
  const busy = status.kind === 'converting' || status.kind === 'combining'

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

  function runDetect(file: File) {
    latestPick.current = file
    // Advisory only. If the check itself fails there is nothing useful to say, so
    // it stays silent rather than showing an error for a file that may convert fine.
    detect(file)
      .then((d) => {
        if (latestPick.current === file) setMismatch(d.mismatch)
      })
      .catch(() => {})
  }

  function addFiles(incoming: FileList | null) {
    const added = Array.from(incoming ?? [])
    if (added.length === 0) return

    setStatus({ kind: 'idle' })
    setResult(null)

    // Appending rather than replacing is what makes the order first-come-first-served
    // across several picks. The backend merges in exactly this order.
    if (files.length === 0) {
      setTarget(null)
      setMismatch(null)
      runDetect(added[0])
    }
    setFiles([...files, ...added])
  }

  function removeAt(index: number) {
    const next = files.filter((_, i) => i !== index)
    setFiles(next)
    setStatus({ kind: 'idle' })
    setResult(null)

    if (next.length === 0) {
      setTarget(null)
      setMismatch(null)
      latestPick.current = null
    } else if (index === 0) {
      // The first file drives everything, so dropping it invalidates the target and
      // the mismatch answer.
      setTarget(null)
      setMismatch(null)
      runDetect(next[0])
    }
  }

  async function run(action: () => Promise<{ blob: Blob; filename: string }>,
                     kind: 'converting' | 'combining') {
    setStatus({ kind })
    setResult(null)
    try {
      const { blob, filename } = await action()
      // Hold the result and let the user click Download, rather than firing the
      // download automatically.
      setResult({ url: URL.createObjectURL(blob), filename })
      setStatus({ kind: 'idle' })
    } catch (e) {
      setStatus({ kind: 'error', message: (e as Error).message })
    }
  }

  const pickerLabel =
    files.length === 0 ? 'Choose or drop a file'
      : files.length === 1 ? files[0].name
        : `${files.length} files`

  return (
    <div className="layout">
      <aside className="sidebar">
        <h2>Convert to</h2>

        <div className="formats">
          {formats?.allFormats.map((f) => {
            const route = routesFor(f.ext)[0]
            const dep = blocked.find((u) => u.ext === f.ext)
            // Every disabled button says why on hover, so a greyed-out list is never
            // just a dead end.
            const why = route
              ? undefined
              : files.length === 0
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
                disabled={!route}
                title={why}
                onClick={() => route && setTarget(route.id)}
              >
                {f.name}
              </button>
            )
          })}
        </div>

        {files.length > 0 && targets.length === 0 && (
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

        <label
          className={dragging ? 'filepicker dragging' : 'filepicker'}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          // dragleave also fires when the cursor crosses onto a child, so without the
          // contains() check the highlight flickers as you move over the label text.
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false)
          }}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            addFiles(e.dataTransfer.files)
          }}
        >
          <input
            type="file"
            multiple
            onChange={(e) => {
              addFiles(e.target.files)
              // Clearing the value lets the same file be picked again after removing
              // it, which otherwise fires no change event.
              e.target.value = ''
            }}
          />
          <span title={files.length === 1 ? files[0].name : undefined}>{pickerLabel}</span>
        </label>

        {files.length > 0 && (
          <ol className="filelist">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`}>
                <span title={f.name}>{f.name}</span>
                <button
                  type="button"
                  className="remove"
                  onClick={() => removeAt(i)}
                  aria-label={`Remove ${f.name}`}
                >
                  &times;
                </button>
              </li>
            ))}
          </ol>
        )}

        {mismatch && (
          <p className="warning">
            This file is named <code>{mismatch.named}</code> but its contents are
            actually <code>{mismatch.actual}</code>. The conversions offered are the
            ones for <code>{mismatch.named}</code>, so they will likely fail or give
            you garbage. Renaming it to <code>{mismatch.actual}</code> will fix it.
          </p>
        )}

        {mixedExtensions && (
          <p className="warning">
            Combining needs every file to be the same format, and these are{' '}
            {distinctExts.join(', ')}. Convert them to a common format first, or
            remove the odd ones out.
          </p>
        )}

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

        <div className="actions">
          <button
            className="action"
            onClick={() => primary && target && run(() => convert(primary, target), 'converting')}
            disabled={files.length !== 1 || !target || busy}
            title={files.length > 1 ? 'Converting takes one file at a time' : undefined}
          >
            {status.kind === 'converting' ? 'Converting...' : 'Convert'}
          </button>

          <button
            className="action"
            onClick={() => run(() => combine(files), 'combining')}
            disabled={!canCombine || busy}
            title={
              files.length < 2
                ? 'Add two or more files to combine'
                : mixedExtensions
                  ? 'Every file has to be the same format'
                  : undefined
            }
          >
            {status.kind === 'combining' ? 'Combining...' : 'Combine files'}
          </button>
        </div>

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
