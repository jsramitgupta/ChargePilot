import { useEffect, useState } from 'react'

export function useAppTheme() {
  const [isDark, setIsDark] = useState(() => {
    const savedTheme = window.localStorage.getItem('chargepilot-theme')
    return savedTheme ? savedTheme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.body.classList.toggle('theme-dark', isDark)
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', isDark ? '#101c19' : '#eef3f0')
    window.localStorage.setItem('chargepilot-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  return [isDark, setIsDark] as const
}
