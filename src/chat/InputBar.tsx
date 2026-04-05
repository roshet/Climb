import { useState, KeyboardEvent } from 'react'

interface InputBarProps {
  onSend: (message: string) => void
  disabled: boolean
}

export function InputBar({ onSend, disabled }: InputBarProps) {
  const [value, setValue] = useState('')

  const submit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="border-t border-white/10 p-3 flex gap-2 items-end">
      <textarea
        className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 resize-none outline-none placeholder-gray-500 min-h-[40px] max-h-[120px]"
        placeholder="Ask anything about your games..."
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        disabled={disabled}
      />
      <button
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl px-3 py-2 text-sm transition-colors"
      >
        ↑
      </button>
    </div>
  )
}
