import { useState } from 'react'

import ChatView from './views/ChatView'
import LearnView from './views/LearnView'

const VIEWS = [
  { id: 'chat', label: 'Chat', blurb: '' },
  { id: 'capture', label: 'Capture', blurb: 'Capture view — coming in Phase 1.3 (notes, pastes, uploads).' },
  { id: 'learn', label: 'Learn', blurb: '' },
  { id: 'work', label: 'Work', blurb: 'Work view — coming in Phase 2 (extraction, accomplishments).' },
  { id: 'practice', label: 'Practice', blurb: 'Practice view — coming in Phase 3 (Learning-mode loop).' },
  { id: 'interview', label: 'Interview', blurb: 'Interview view — coming in Phase 3 (Interview-mode loop).' },
] as const

type ViewId = (typeof VIEWS)[number]['id']

function App() {
  const [view, setView] = useState<ViewId>('chat')
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
      </header>
      <main className="mt-6">
        {view === 'chat' ? <ChatView /> : view === 'learn' ? <LearnView /> : <p>{active.blurb}</p>}
      </main>
    </div>
  )
}

export default App
