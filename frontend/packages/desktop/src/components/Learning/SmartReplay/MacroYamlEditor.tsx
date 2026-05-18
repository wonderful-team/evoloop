/**
 * MacroYamlEditor - YAML editor for macro scripts using Monaco Editor
 * 
 * Features:
 * - Full Monaco Editor (VS Code) experience
 * - YAML syntax highlighting
 * - Real-time validation
 * - Auto-formatting
 * - Auto-sync (no manual apply needed)
 * - Line numbers, minimap, folding
 */

import { useState, useCallback, useEffect, useRef } from "react"
import { load, dump } from "js-yaml"
import { AlertCircle, Check, FileCode, RotateCcw, Wand2 } from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import { Alert, AlertDescription } from "@evoloop/shared/components/ui/alert"
import { useTranslation } from "react-i18next"
import type { MacroStep } from "./MacroEditor"
import MonacoEditor from "../../Common/MonacoEditor"


interface MacroYamlEditorProps {
    steps: MacroStep[]
    onChange: (steps: MacroStep[]) => void
    readOnly?: boolean
}

const DEFAULT_YAML_TEMPLATE = `version: "1.0"
metadata:
  format: evoloop-macro
  step_count: 0

steps:
  # Example step - replace with your own
  - type: action
    event_type: navigate
    source: dom
    description: Navigate to target page
    payload:
      url: "https://example.com"
`

export function MacroYamlEditor({ steps, onChange, readOnly = false }: MacroYamlEditorProps) {
    const { t } = useTranslation()
    const [yamlValue, setYamlValue] = useState("")
    const [error, setError] = useState<string | null>(null)
    const [isValid, setIsValid] = useState(true)
    const editorRef = useRef<{ getValue: () => string; setValue: (v: string) => void } | null>(null)
    const syncTimeoutRef = useRef<NodeJS.Timeout | null>(null)

    // Convert steps to YAML on mount or when steps change externally
    useEffect(() => {
        try {
            const yaml = dump({
                version: "1.0",
                metadata: {
                    format: "evoloop-macro",
                    step_count: steps.length
                },
                steps
            }, {
                indent: 2,
                lineWidth: -1,
                noRefs: true,
                sortKeys: false
            })
            setYamlValue(yaml)
            setError(null)
            setIsValid(true)
        } catch (e) {
            setError(t("macroEditor.yamlConvertError"))
            setIsValid(false)
        }
    }, [steps, t])

    // Cleanup timeout on unmount
    useEffect(() => {
        return () => {
            if (syncTimeoutRef.current) {
                clearTimeout(syncTimeoutRef.current)
            }
        }
    }, [])

    const validateAndSync = useCallback((content: string) => {
        try {
            const parsed = load(content)
            
            if (!parsed || typeof parsed !== "object") {
                setError(t("macroEditor.yamlRootObject"))
                setIsValid(false)
                return
            }
            
            const data = parsed as Record<string, unknown>
            const stepsData = data.steps || data
            
            if (!Array.isArray(stepsData)) {
                setError(t("macroEditor.yamlStepsArray"))
                setIsValid(false)
                return
            }
            
            // Validate each step
            for (let i = 0; i < stepsData.length; i++) {
                const step = stepsData[i]
                if (!step || typeof step !== "object") {
                    setError(t("macroEditor.yamlStepObject", { index: i + 1 }))
                    setIsValid(false)
                    return
                }
                const stepObj = step as Record<string, unknown>
                if (!stepObj.type) {
                    setError(t("macroEditor.yamlStepTypeMissing", { index: i + 1 }))
                    setIsValid(false)
                    return
                }
            }
            
            // Valid - sync to parent
            setError(null)
            setIsValid(true)
            
            // Re-number steps sequentially
            const renumberedSteps = stepsData.map((step, index) => ({
                ...step,
                step_number: index + 1
            }))
            
            onChange(renumberedSteps)
        } catch (e: any) {
            setError(e.message)
            setIsValid(false)
        }
    }, [onChange, t])

    const handleEditorChange = useCallback((value: string | undefined) => {
        const newValue = value || ""
        setYamlValue(newValue)
        
        // Debounce sync to avoid performance issues
        if (syncTimeoutRef.current) {
            clearTimeout(syncTimeoutRef.current)
        }
        syncTimeoutRef.current = setTimeout(() => {
            validateAndSync(newValue)
        }, 300)
    }, [validateAndSync])

    // No need for mount handler with new MonacoEditor

    const handleFormat = useCallback(() => {
        try {
            const parsed = load(yamlValue)
            const formatted = dump(parsed, {
                indent: 2,
                lineWidth: -1,
                noRefs: true,
                sortKeys: false
            })
            setYamlValue(formatted)
            setError(null)
            setIsValid(true)
            // Sync immediately after format
            validateAndSync(formatted)
            // Update editor content
            editorRef.current?.setValue(formatted)
        } catch (e: any) {
            setError(e.message)
            setIsValid(false)
        }
    }, [yamlValue, validateAndSync])

    const handleReset = useCallback(() => {
        try {
            const yaml = dump({
                version: "1.0",
                metadata: {
                    format: "evoloop-macro",
                    step_count: steps.length
                },
                steps
            }, {
                indent: 2,
                lineWidth: -1,
                noRefs: true,
                sortKeys: false
            })
            setYamlValue(yaml)
            setError(null)
            setIsValid(true)
            editorRef.current?.setValue(yaml)
        } catch (e) {
            setError(t("macroEditor.yamlConvertError"))
        }
    }, [steps, t])

    const handleLoadTemplate = useCallback(() => {
        setYamlValue(DEFAULT_YAML_TEMPLATE)
        editorRef.current?.setValue(DEFAULT_YAML_TEMPLATE)
        // Sync immediately
        validateAndSync(DEFAULT_YAML_TEMPLATE)
    }, [validateAndSync])

    const stepCount = (() => {
        try {
            const parsed = load(yamlValue) as Record<string, unknown> | null
            const stepsData = parsed?.steps || parsed
            return Array.isArray(stepsData) ? stepsData.length : 0
        } catch {
            return 0
        }
    })()

    return (
        <div className="flex flex-col h-full">
            {/* Toolbar */}
            {!readOnly && (
                <div className="flex items-center justify-between p-2 border-b border-border bg-muted/30 shrink-0">
                    <div className="flex items-center gap-2">
                        <FileCode className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm font-medium">YAML</span>
                        <span className="text-xs text-muted-foreground">
                            ({t("macroEditor.autoSync")})
                        </span>
                    </div>
                    <div className="flex items-center gap-1">
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleLoadTemplate}
                            title={t("macroEditor.loadTemplate")}
                        >
                            <Wand2 className="h-4 w-4 mr-1" />
                            {t("macroEditor.template")}
                        </Button>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleReset}
                            title={t("macroEditor.reset")}
                        >
                            <RotateCcw className="h-4 w-4 mr-1" />
                            {t("macroEditor.reset")}
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleFormat}
                            disabled={!isValid}
                        >
                            {t("macroEditor.format")}
                        </Button>
                    </div>
                </div>
            )}

            {/* Error Alert */}
            {error && (
                <Alert variant="destructive" className="m-2 shrink-0">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription className="font-mono text-xs">{error}</AlertDescription>
                </Alert>
            )}

            {/* Monaco Editor */}
            <div className="flex-1 min-h-0">
                <MonacoEditor
                    ref={editorRef}
                    language="yaml"
                    value={yamlValue}
                    onChange={handleEditorChange}
                    readOnly={readOnly}
                />
            </div>

            {/* Status Bar */}
            <div className="flex items-center justify-between px-3 py-1.5 border-t bg-muted/20 text-xs text-muted-foreground shrink-0">
                <div className="flex items-center gap-4">
                    <span>
                        {isValid ? (
                            <span className="text-emerald-600 flex items-center gap-1">
                                <Check className="h-3 w-3" />
                                {t("macroEditor.valid")}
                            </span>
                        ) : (
                            <span className="text-destructive flex items-center gap-1">
                                <AlertCircle className="h-3 w-3" />
                                {t("macroEditor.invalid")}
                            </span>
                        )}
                    </span>
                    <span>
                        {t("macroEditor.steps", { count: stepCount })}
                    </span>
                </div>
                <div className="font-mono opacity-50">
                    YAML v1.0
                </div>
            </div>
        </div>
    )
}
