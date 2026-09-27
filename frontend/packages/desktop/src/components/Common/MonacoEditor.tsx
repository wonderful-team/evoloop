/**
 * Monaco Editor wrapper
 *
 * Direct import of monaco-editor (no CDN, no react wrapper)
 * - Consistent styling and options
 * - Native context menu (Monaco's context menu disabled)
 */

import type * as monaco from "monaco-editor"
import {forwardRef, useEffect, useImperativeHandle, useRef} from "react"

interface MonacoEditorProps {
  value: string
  onChange?: (value: string) => void
  language?: string
  readOnly?: boolean
  placeholder?: string
  theme?: "vs" | "vs-dark" | "hc-black"
  options?: monaco.editor.IStandaloneEditorConstructionOptions
}

interface MonacoEditorRef {
  getValue: () => string
  setValue: (value: string) => void
}

// Dynamic import to avoid SSR issues
let monacoInstance: typeof monaco | null = null
const loadMonaco = async () => {
  if (!monacoInstance) {
    monacoInstance = await import("monaco-editor")

    // Configure YAML language support
    monacoInstance.languages.register({ id: "yaml" })

    // Configure Markdown language support
    monacoInstance.languages.register({ id: "markdown" })
  }
  return monacoInstance
}

const MonacoEditor = forwardRef<MonacoEditorRef, MonacoEditorProps>(
  function MonacoEditor(
    {
      value,
      onChange,
      language = "text",
      readOnly = false,
      theme = "vs-dark",
      options,
    },
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement>(null)
    const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)

    useImperativeHandle(ref, () => ({
      getValue: () => editorRef.current?.getValue() || "",
      setValue: (v: string) => editorRef.current?.setValue(v),
    }))

    // Initialize editor
    useEffect(() => {
      let mounted = true
      let resizeObserver: ResizeObserver | null = null
      let resizeTimeout: NodeJS.Timeout | null = null

      const init = async () => {
        const monaco = await loadMonaco()
        if (!mounted || !containerRef.current) return

        const editor = monaco.editor.create(containerRef.current, {
          value,
          language,
          theme,
          readOnly,
          minimap: { enabled: false },
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          automaticLayout: false,
          tabSize: 2,
          insertSpaces: true,
          fontSize: 13,
          fontFamily:
            "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          padding: { top: 12, bottom: 12 },
          folding: true,
          wordWrap: "on",
          contextmenu: false,
          ...options,
        })

        if (!mounted) {
          editor.dispose()
          return
        }

        editorRef.current = editor

        // Listen for changes
        editor.onDidChangeModelContent(() => {
          onChange?.(editor.getValue())
        })

        // Initial layout
        editor.layout()

        // Manual resize observer with debounce
        resizeObserver = new ResizeObserver(() => {
          if (resizeTimeout) clearTimeout(resizeTimeout)
          resizeTimeout = setTimeout(() => {
            editor.layout()
          }, 100)
        })

        resizeObserver.observe(containerRef.current)
      }

      init()

      return () => {
        mounted = false
        resizeObserver?.disconnect()
        if (resizeTimeout) clearTimeout(resizeTimeout)
        editorRef.current?.dispose()
        editorRef.current = null
      }
    }, [])

    // Update value when prop changes
    useEffect(() => {
      if (editorRef.current && editorRef.current.getValue() !== value) {
        editorRef.current.setValue(value)
      }
    }, [value])

    // Update theme
    useEffect(() => {
      monacoInstance?.editor.setTheme(theme)
    }, [theme])

    // Update readOnly
    useEffect(() => {
      editorRef.current?.updateOptions({ readOnly })
    }, [readOnly])

    return <div ref={containerRef} className="h-full w-full min-h-[100px]" />
  },
)

export default MonacoEditor
