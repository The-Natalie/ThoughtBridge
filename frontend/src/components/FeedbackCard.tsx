import type { GroundingLabel, PracticeFeedback } from '../api/types'

interface FeedbackCardProps {
  feedback: PracticeFeedback
  grounding: GroundingLabel
}

const GROUNDING_STYLES: Record<GroundingLabel, string> = {
  'from your notes': 'border-green-600',
  'general explanation': 'border-neutral-400',
  both: 'border-blue-600',
}

function FeedbackSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mt-2">
      <h4 className="text-xs font-semibold">{title}</h4>
      {items.length > 0 ? (
        <ul className="mt-1 list-disc pl-5 text-sm">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm italic">(none)</p>
      )}
    </div>
  )
}

/** Shared practice-feedback display: five sections plus the grounding badge. */
function FeedbackCard({ feedback, grounding }: FeedbackCardProps) {
  return (
    <div aria-label="Feedback" className="rounded border px-3 py-2">
      <p aria-label="Grounding" className={`inline-block rounded border px-2 py-0.5 text-xs ${GROUNDING_STYLES[grounding]}`}>
        {grounding}
      </p>
      <FeedbackSection title="Correct" items={feedback.correct} />
      <FeedbackSection title="Missing" items={feedback.missing} />
      <FeedbackSection title="Inaccurate" items={feedback.inaccurate} />
      <FeedbackSection title="Terminology help" items={feedback.terminology} />
      <div className="mt-2">
        <h4 className="text-xs font-semibold">Next step</h4>
        <p className="mt-1 text-sm font-medium">{feedback.next_step}</p>
      </div>
    </div>
  )
}

export default FeedbackCard
