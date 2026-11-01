import { Moon, Sun } from 'lucide-react'

export function ThemeToggleButton({
  isDark,
  onToggle,
  className = '',
}: {
  isDark: boolean
  onToggle: () => void
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`theme-toggle ${className}`}
      aria-label={isDark ? 'Use light theme' : 'Use dark theme'}
      aria-pressed={isDark}
    >
      {isDark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
    </button>
  )
}
