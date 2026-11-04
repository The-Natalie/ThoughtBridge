import { useState } from 'react'

import CheckpointPromptModal from './components/CheckpointPromptModal'
import CaptureView from './views/CaptureView'
import ChatView from './views/ChatView'
import InterviewView from './views/InterviewView'
import LearnView from './views/LearnView'
import PracticeView from './views/PracticeView'
import WorkView from './views/WorkView'

const VIEWS = [
  { id: 'chat', label: 'Chat', blurb: '' },
  { id: 'capture', label: 'Capture', blurb: '' },
  { id: 'learn', label: 'Learn', blurb: '' },
  { id: 'work', label: 'Work', blurb: '' },
  { id: 'practice', label: 'Practice', blurb: '' },
  { id: 'interview', label: 'Interview', blurb: '' },
] as const

type ViewId = (typeof VIEWS)[number]['id']

function App() {
  const [view, setView] = useState<ViewId>('chat')
  const [checkpointOpen, setCheckpointOpen] = useState(false)
  const active = VIEWS.find((v) => v.id === view) ?? VIEWS[0]

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col p-6">
      <header>
        <h1 className="text-2xl font-semibold">ThoughtBridge</h1>
        <nav className="mt-3 flex gap-2" aria-label="Primary">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => setView(v.id)}
              aria-pressed={v.id === view}
              className={`rounded border px-3 py-1 text-sm ${
                v.id === view ? 'font-semibold underline' : ''
              }`}
            >
              {v.label}
            </button>
          ))}
        </nav>
        <button
          type="button"
          aria-label="Checkpoint prompt"
          onClick={() => setCheckpointOpen(true)}
          className="mt-3 rounded border px-3 py-1 text-sm"
        >
          Checkpoint prompt
        </button>
      </header>
      {checkpointOpen && <CheckpointPromptModal onClose={() => setCheckpointOpen(false)} />}
      <main className="mt-6">
        {view === 'chat' ? (
          <ChatView />
        ) : view === 'capture' ? (
          <CaptureView />
        ) : view === 'learn' ? (
          <LearnView />
        ) : view === 'work' ? (
          <WorkView />
        ) : view === 'practice' ? (
          <PracticeView />
        ) : view === 'interview' ? (
          <InterviewView />
        ) : (
          <p>{active.blurb}</p>
        )}
      </main>
    </div>
  )
}

export default App
