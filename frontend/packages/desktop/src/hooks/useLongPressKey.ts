import { useState, useRef, useCallback, useEffect } from 'react'

interface UseLongPressKeyOptions {
  targetKey?: string
  duration?: number
  onLongPressStart?: () => void
  onLongPressEnd?: () => void
  enabled?: boolean
}

interface UseLongPressKeyReturn {
  isPressed: boolean
  isLongPressed: boolean
  error: string | null
}

// Browser-compatible version (for regular keys)
export function useLongPressKey(options: UseLongPressKeyOptions = {}): UseLongPressKeyReturn {
  const {
    targetKey = 'Fn',
    duration = 500,
    onLongPressStart,
    onLongPressEnd,
    enabled = true
  } = options

  const [isPressed, setIsPressed] = useState(false)
  const [isLongPressed, setIsLongPressed] = useState(false)
  const [error] = useState<string | null>(null)

  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const isLongPressTriggeredRef = useRef(false)

  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return

    // Note: Fn key cannot be detected in browsers
    // We'll use Space or Alt as fallback for browser testing
    const effectiveKey = targetKey === 'Fn' ? 'Alt' : targetKey

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === effectiveKey && !isPressed) {
        event.preventDefault()
        setIsPressed(true)
        isLongPressTriggeredRef.current = false

        timerRef.current = setTimeout(() => {
          setIsLongPressed(true)
          isLongPressTriggeredRef.current = true
          onLongPressStart?.()
        }, duration)
      }
    }

    const handleKeyUp = (event: KeyboardEvent) => {
      if (event.key === effectiveKey) {
        event.preventDefault()
        setIsPressed(false)

        if (timerRef.current) {
          clearTimeout(timerRef.current)
          timerRef.current = null
        }

        if (isLongPressTriggeredRef.current) {
          setIsLongPressed(false)
          onLongPressEnd?.()
          isLongPressTriggeredRef.current = false
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
    }
  }, [targetKey, duration, onLongPressStart, onLongPressEnd, enabled, isPressed])

  return { isPressed, isLongPressed, error }
}

// Settings hook
export function useLongPressSettings() {
  const [longPressKey, setLongPressKey] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('evoloop_long_press_key') || 'Fn'
    }
    return 'Fn'
  })

  const [longPressDuration, setLongPressDuration] = useState(() => {
    if (typeof window !== 'undefined') {
      return parseInt(localStorage.getItem('evoloop_long_press_duration') || '500')
    }
    return 500
  })

  const [longPressEnabled, setLongPressEnabled] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('evoloop_long_press_enabled') === 'true'
    }
    return false
  })

  const updateLongPressKey = useCallback((key: string) => {
    setLongPressKey(key)
    localStorage.setItem('evoloop_long_press_key', key)
  }, [])

  const updateLongPressDuration = useCallback((duration: number) => {
    setLongPressDuration(duration)
    localStorage.setItem('evoloop_long_press_duration', duration.toString())
  }, [])

  const toggleLongPress = useCallback(() => {
    setLongPressEnabled(prev => {
      const newValue = !prev
      localStorage.setItem('evoloop_long_press_enabled', newValue.toString())
      return newValue
    })
  }, [])

  return {
    longPressKey,
    longPressDuration,
    longPressEnabled,
    updateLongPressKey,
    updateLongPressDuration,
    toggleLongPress
  }
}
