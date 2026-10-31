import type { Answers, Question } from '../services/api'

type Props = { questions: Question[]; answers: Answers; onChange: (answers: Answers) => void; disabled?: boolean }

export default function Questionnaire({ questions, answers, onChange, disabled }: Props) {
  function set(id: string, value: string | string[]) {
    const next = { ...answers }
    if (value.length === 0) delete next[id]
    else next[id] = value
    onChange(next)
  }
  return (
    <div className="questionnaire">
      {questions.map(question => {
        const current = answers[question.id]
        return question.type === 'single' ? (
          <div className="question" key={question.id}>
            <label htmlFor={`q-${question.id}`}>{question.label}</label>
            <select id={`q-${question.id}`} value={typeof current === 'string' ? current : ''} disabled={disabled} onChange={event => set(question.id, event.target.value)}>
              <option value="">선택 안 함</option>
              {question.options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
        ) : (
          <fieldset className="question" key={question.id} disabled={disabled}>
            <legend>{question.label}</legend>
            <div className="question-options">
              {question.options.map(option => {
                const selected = Array.isArray(current) ? current : []
                return <label key={option.value}><input type="checkbox" checked={selected.includes(option.value)}
                  onChange={event => set(question.id, event.target.checked ? [...selected, option.value] : selected.filter(value => value !== option.value))} />{option.label}</label>
              })}
            </div>
          </fieldset>
        )
      })}
    </div>
  )
}
