import React, { useRef, useState } from 'react'

export default function App() {
  const [recording, setRecording] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [summary, setSummary] = useState('')
  const [actionItems, setActionItems] = useState([])
  const [status, setStatus] = useState('idle')
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])

  async function startRecording() {
    setTranscript('')
    setStatus('requesting_mic')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      mediaRecorderRef.current = mr
      chunksRef.current = []

      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data)
      }

      mr.onstop = async () => {
        setStatus('uploading')
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        const fd = new FormData()
        // Name the file so backend has an extension it can inspect
        fd.append('file', blob, 'meeting.webm')

        try {
          const res = await fetch('http://127.0.0.1:8000/upload-audio', {
            method: 'POST',
            body: fd,
          })
          const json = await res.json()
          setTranscript(json.transcription || JSON.stringify(json))
          setStatus('done')
        } catch (err) {
          setTranscript('Error uploading/transcribing: ' + err.message)
          setStatus('error')
        }
      }

      mr.start()
      setRecording(true)
      setStatus('recording')
    } catch (err) {
      setStatus('mic_error')
      setTranscript('Microphone access denied or not available: ' + err.message)
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
      // stop all tracks to release mic
      mediaRecorderRef.current.stream && mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop())
    }
    setRecording(false)
    setStatus('stopped')
  }

  return (
    <div className="app">
      <header>
        <h1>Meeting Recorder — Speak to transcribe</h1>
        <p className="tag">Press Record, speak into your microphone, then Stop to send audio to the backend for transcription.</p>
      </header>

      <main>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={startRecording} disabled={recording} style={{ padding: '8px 12px' }}>Record</button>
          <button onClick={stopRecording} disabled={!recording} style={{ padding: '8px 12px' }}>Stop</button>
          <div style={{ marginLeft: 12 }}><strong>Status:</strong> {status}</div>
        </div>

        <section style={{ marginTop: 20 }}>
          <h3>Transcription</h3>
          <div style={{ whiteSpace: 'pre-wrap', background: '#fafafa', padding: 12, borderRadius: 6, minHeight: 120 }}>{transcript || <em>No transcription yet</em>}</div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button
              onClick={async () => {
                if (!transcript) return
                setStatus('saving')
                try {
                  const res = await fetch('http://127.0.0.1:8000/save-transcript', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename: 'transcript.txt', content: transcript }),
                  })
                  const j = await res.json()
                  if (res.ok) {
                    setStatus('saved')
                    setTranscript(prev => prev + '\n\n[Saved to Drive] ' + (j.file.webViewLink || j.file.id))
                  } else {
                    setStatus('save_error')
                    setTranscript(prev => prev + '\n\n[Save error] ' + JSON.stringify(j))
                  }
                } catch (err) {
                  setStatus('save_error')
                  setTranscript(prev => prev + '\n\n[Save error] ' + err.message)
                }
              }}
              disabled={!transcript || status === 'saving'}
              style={{ padding: '6px 10px', marginTop: 8 }}
            >
              Save to Google Drive
            </button>

            <button
              onClick={async () => {
                if (!transcript) return
                setStatus('summarizing')
                try {
                  const res = await fetch('http://127.0.0.1:8000/summarize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: transcript, num_sentences: 3 }),
                  })
                  const j = await res.json()
                  if (res.ok) {
                    setSummary(j.summary || '')
                    setActionItems(j.action_items || [])
                    setStatus('summarized')
                  } else {
                    setSummary('Error summarizing: ' + JSON.stringify(j))
                    setStatus('summary_error')
                  }
                } catch (err) {
                  setSummary('Error summarizing: ' + err.message)
                  setStatus('summary_error')
                }
              }}
              disabled={!transcript || status === 'summarizing'}
              style={{ padding: '6px 10px', marginTop: 8 }}
            >
              Summarize
            </button>
          </div>
          {summary && (
            <div style={{ marginTop: 12 }}>
              <h4>Summary</h4>
              <div style={{ whiteSpace: 'pre-wrap', background: '#fff8dc', padding: 12, borderRadius: 6 }}>{summary}</div>
            </div>
          )}
          {actionItems && actionItems.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <h4>Action Items</h4>
              <ul>{actionItems.map((it, i) => <li key={i}>{it}</li>)}</ul>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
