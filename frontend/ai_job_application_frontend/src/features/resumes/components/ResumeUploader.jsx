import { LoaderCircle, Upload } from 'lucide-react'
import { useRef, useState } from 'react'

import { cn } from '@/lib/utils'

import { checkResumeFile } from '../api'
import { useUploadResume } from '../hooks'

/** Drag & drop (or click) to upload a PDF/DOCX as a new resume version. */
export function ResumeUploader() {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [problem, setProblem] = useState(null)
  const upload = useUploadResume()

  function send(file) {
    if (!file) return
    const error = checkResumeFile(file)
    setProblem(error)
    if (!error) upload.mutate(file, { onError: (e) => setProblem(e.message) })
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          send(event.dataTransfer.files?.[0])
        }}
        disabled={upload.isPending}
        className={cn(
          'flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors',
          'hover:border-primary/60 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          dragging && 'border-primary bg-accent/60',
        )}
      >
        {upload.isPending ? (
          <LoaderCircle className="size-6 animate-spin text-primary" aria-hidden="true" />
        ) : (
          <Upload className="size-6 text-primary" aria-hidden="true" />
        )}
        <span className="font-medium">
          {upload.isPending ? 'Uploading…' : 'Drop your resume here or click to choose'}
        </span>
        <span className="text-xs text-muted-foreground">PDF or DOCX, up to 5 MB</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="hidden"
        data-testid="resume-file-input"
        onChange={(event) => {
          send(event.target.files?.[0])
          event.target.value = ''
        }}
      />
      {problem && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {problem}
        </p>
      )}
    </div>
  )
}
