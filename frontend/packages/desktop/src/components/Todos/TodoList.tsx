import { useEffect, useState, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Input } from "@evoloop/shared/components/ui/input"
import { Check, Trash2, Calendar as CalendarIcon, Plus, SortAsc, LayoutGrid, List as ListIcon, MessageSquare, Filter, Zap } from "lucide-react"

import { TodosService, type TodoResponse, type TodoStatus, type TodoPriority } from "../../client"
import { Button } from "@evoloop/shared/components/ui/button"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@evoloop/shared/components/ui/select"
import { Popover, PopoverContent, PopoverTrigger } from "@evoloop/shared/components/ui/popover"
import { Calendar } from "@evoloop/shared/components/ui/calendar"
import { cn } from "@evoloop/shared/lib/utils"
import { toast } from "sonner"
import { format } from "date-fns"
import { zhCN, enUS } from "date-fns/locale"
import { Link } from "@tanstack/react-router"
import { useProjectStore } from "@/stores/projectStore"

export function TodoList() {
    const { t, i18n } = useTranslation()
    const { currentProject } = useProjectStore()
    const [todos, setTodos] = useState<TodoResponse[]>([])
    const [loading, setLoading] = useState(false)
    const [view, setView] = useState<"list" | "calendar">("list")

    // Filter State
    const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "completed">("all")
    const [priorityFilter, setPriorityFilter] = useState<"all" | TodoPriority>("all")
    const [categoryFilter, setCategoryFilter] = useState<string | null>(null)

    // Create State
    const [newTitle, setNewTitle] = useState("")
    const [newPriority, setNewPriority] = useState<TodoPriority>('medium' as TodoPriority)
    const [newCategory, setNewCategory] = useState("")
    const [newDueDate, setNewDueDate] = useState<Date | undefined>(undefined)
    const [isCreating, setIsCreating] = useState(false)

    // Sort State
    const [sortBy, setSortBy] = useState<"created" | "priority" | "date">("created")

    const fetchTodos = async () => {
        setLoading(true)
        try {
            // Fetch all todos for client-side filtering (or filter by project?)
            // For now, let's fetch ALL todos to show a comprehensive list, but we could scope it.
            // const data = await TodosService.listTodos({ status: undefined, projectId: currentProject?.id })
            const data = await TodosService.listTodos({ status: undefined })
            setTodos(data)
        } catch (error) {
            console.error("Failed to fetch todos", error)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchTodos()
        const interval = setInterval(fetchTodos, 30000)
        return () => clearInterval(interval)
    }, [])

    const getDateLocale = () => {
        return i18n.language === 'zh' ? zhCN : enUS
    }

    const handleCreateTodo = async (e?: React.FormEvent) => {
        e?.preventDefault()
        if (!newTitle.trim()) return

        setIsCreating(true)
        try {
            const newTodo = await TodosService.createTodo({
                requestBody: {
                    title: newTitle,
                    priority: newPriority,
                    category: newCategory || undefined,
                    due_date: newDueDate ? newDueDate.toISOString() : undefined,
                    // @ts-ignore - project_id added to backend but SDK not regenerated
                    project_id: currentProject?.id
                }
            })
            setTodos(prev => [newTodo, ...prev])
            setNewTitle("")
            setNewPriority('medium' as TodoPriority)
            setNewCategory("")
            setNewDueDate(undefined)
            toast.success(t("todos.create.success"))
        } catch (error) {
            toast.error(t("todos.create.error"))
        } finally {
            setIsCreating(false)
        }
    }

    const handleStatusChange = async (id: string, currentStatus: TodoStatus) => {
        const newStatus = currentStatus === 'completed' as TodoStatus ? 'pending' as TodoStatus : 'completed' as TodoStatus
        setTodos(prev => prev.map(t => t.id === id ? { ...t, status: newStatus } : t))
        try {
            await TodosService.updateTodo({ todoId: id, requestBody: { status: newStatus } })
            toast.success(t("todos.update.success"))
        } catch (error) {
            toast.error(t("todos.update.error"))
            fetchTodos()
        }
    }

    const handleDelete = async (id: string) => {
        setTodos(prev => prev.filter(t => t.id !== id))
        try {
            await TodosService.deleteTodo({ todoId: id })
            toast.success(t("todos.delete.success"))
        } catch (error) {
            toast.error(t("todos.delete.error"))
            fetchTodos()
        }
    }

    // Derived State
    const uniqueCategories = useMemo(() => {
        const cats = new Set<string>()
        todos.forEach(t => {
            if (t.category) cats.add(t.category)
        })
        return Array.from(cats).sort()
    }, [todos])

    const filteredTodos = useMemo(() => {
        return todos.filter(t => {
            // Status Filter
            if (statusFilter !== 'all' && t.status !== statusFilter) return false
            // Priority Filter
            if (priorityFilter !== 'all' && t.priority !== priorityFilter) return false
            // Category Filter
            if (categoryFilter && t.category !== categoryFilter) return false
            return true
        })
    }, [todos, statusFilter, priorityFilter, categoryFilter])

    // Sorting Logic
    const sortedTodos = useMemo(() => {
        return [...filteredTodos].sort((a, b) => {
            if (sortBy === 'priority') {
                const pMap = { high: 3, medium: 2, low: 1 }
                return (pMap[b.priority] || 0) - (pMap[a.priority] || 0)
            }
            if (sortBy === 'date') {
                if (!a.due_date) return 1
                if (!b.due_date) return -1
                return new Date(a.due_date).getTime() - new Date(b.due_date).getTime()
            }
            // Default created (newest first)
            return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        })
    }, [filteredTodos, sortBy])

    const getPriorityColor = (priority: TodoPriority) => {
        switch (priority) {
            case 'high' as TodoPriority: return 'text-red-500 bg-red-500/10 border-red-500/20'
            case 'medium' as TodoPriority: return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'
            case 'low' as TodoPriority: return 'text-green-500 bg-green-500/10 border-green-500/20'
            default: return 'text-muted-foreground'
        }
    }

    const formatDueDate = (dateStr?: string | null) => {
        if (!dateStr) return null
        return format(new Date(dateStr), "PPP", { locale: getDateLocale() })
    }

    // Calendar View Rendering
    const renderCalendarView = () => {
        // Group by date
        const todosByDate: Record<string, TodoResponse[]> = {}
        sortedTodos.forEach(t => {
            if (t.due_date) {
                const dateKey = format(new Date(t.due_date), 'yyyy-MM-dd')
                if (!todosByDate[dateKey]) todosByDate[dateKey] = []
                todosByDate[dateKey].push(t)
            } else {
                if (!todosByDate['No Date']) todosByDate['No Date'] = []
                todosByDate['No Date'].push(t)
            }
        })

        return (
            <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {Object.entries(todosByDate).sort().map(([date, items]) => (
                    <div key={date} className="border rounded-lg p-3 bg-card/50">
                        <h4 className="font-medium text-sm mb-2 border-b pb-1 opacity-80">
                            {date === 'No Date'
                                ? t('todos.noDueDate')
                                : format(new Date(date), 'EEE, MMM d', { locale: getDateLocale() })}
                        </h4>
                        <div className="space-y-2">
                            {items.map(todo => (
                                <div key={todo.id} className="flex items-center gap-2 text-xs border p-1.5 rounded bg-background">
                                    <div className={cn("w-2 h-2 rounded-full",
                                        todo.priority === 'high' as TodoPriority ? "bg-red-500" :
                                            todo.priority === 'medium' as TodoPriority ? "bg-yellow-500" : "bg-green-500"
                                    )} />
                                    <span className={cn("truncate flex-1", todo.status === 'completed' as TodoStatus && "line-through opacity-50")}>{todo.title}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        )
    }

    const getHeaderTitle = () => {
        switch (statusFilter) {
            case 'pending': return t('todos.headers.pendingTasks')
            case 'completed': return t('todos.headers.completedTasks')
            default: return t('todos.headers.allTasks')
        }
    }

    return (
        <div className="flex h-full w-full bg-background overflow-hidden">
            {/* LEFT SIDEBAR: Filters */}
            <div className="w-64 border-r border-border bg-muted/10 p-4 flex flex-col gap-6 shrink-0 h-full overflow-y-auto">
                <div className="flex items-center gap-2 font-semibold text-lg px-2">
                    <Filter className="w-5 h-5" />
                    {t('todos.filters')}
                </div>

                {/* Status Filter */}
                <div className="space-y-2">
                    <h4 className="text-sm font-medium text-muted-foreground px-2">{t('todos.status.title')}</h4>
                    <div className="flex flex-col gap-1">
                        <Button
                            variant={statusFilter === 'all' ? "secondary" : "ghost"}
                            className="justify-start h-8 text-sm"
                            onClick={() => setStatusFilter('all')}
                        >
                            <ListIcon className="w-4 h-4 mr-1.5 opacity-70" /> {t('todos.status.all')}
                        </Button>
                        <Button
                            variant={statusFilter === 'pending' ? "secondary" : "ghost"}
                            className="justify-start h-8 text-sm"
                            onClick={() => setStatusFilter('pending')}
                        >
                            <div className="w-4 h-4 mr-1.5 rounded-full border border-muted-foreground/60" /> {t('todos.status.pending')}
                        </Button>
                        <Button
                            variant={statusFilter === 'completed' ? "secondary" : "ghost"}
                            className="justify-start h-8 text-sm"
                            onClick={() => setStatusFilter('completed')}
                        >
                            <Check className="w-4 h-4 mr-1.5 opacity-70" /> {t('todos.status.completed')}
                        </Button>
                    </div>
                </div>

                {/* Priority Filter */}
                <div className="space-y-2">
                    <h4 className="text-sm font-medium text-muted-foreground px-2">{t('todos.priority.title')}</h4>
                    <div className="flex flex-col gap-1">
                        <Button
                            variant={priorityFilter === 'all' ? "secondary" : "ghost"}
                            className="justify-start h-8 text-sm"
                            onClick={() => setPriorityFilter('all')}
                        >
                            {t('todos.priority.all')}
                        </Button>
                        <Button
                            variant={priorityFilter === 'high' as TodoPriority ? "secondary" : "ghost"}
                            className="justify-start h-8 text-sm"
                            onClick={() => setPriorityFilter('high' as TodoPriority)}
                        >
                            <span className="w-2 h-2 rounded-full bg-red-500 mr-2" /> {t('todos.priority.high')}
                        </Button>
                        <Button
                            variant={priorityFilter === 'medium' as TodoPriority ? "secondary" : "ghost"}
                            className="justify-start h-8 text-sm"
                            onClick={() => setPriorityFilter('medium' as TodoPriority)}
                        >
                            <span className="w-2 h-2 rounded-full bg-yellow-500 mr-2" /> {t('todos.priority.medium')}
                        </Button>
                        <Button
                            variant={priorityFilter === 'low' as TodoPriority ? "secondary" : "ghost"}
                            className="justify-start h-8 text-sm"
                            onClick={() => setPriorityFilter('low' as TodoPriority)}
                        >
                            <span className="w-2 h-2 rounded-full bg-green-500 mr-2" /> {t('todos.priority.low')}
                        </Button>
                    </div>
                </div>

                {/* Category Filter */}
                {uniqueCategories.length > 0 && (
                    <div className="space-y-2">
                        <h4 className="text-sm font-medium text-muted-foreground px-2">{t('todos.category.title')}</h4>
                        <ScrollArea className="h-[200px]">
                            <div className="flex flex-col gap-1">
                                <Button
                                    variant={categoryFilter === null ? "secondary" : "ghost"}
                                    className="justify-start h-8 text-sm"
                                    onClick={() => setCategoryFilter(null)}
                                >
                                    {t('todos.category.all')}
                                </Button>
                                {uniqueCategories.map(cat => (
                                    <Button
                                        key={cat}
                                        variant={categoryFilter === cat ? "secondary" : "ghost"}
                                        className="justify-start h-8 text-sm truncate"
                                        onClick={() => setCategoryFilter(cat)}
                                    >
                                        <span className="text-xs bg-muted border px-1.5 rounded mr-2 opacity-70">#</span> {cat}
                                    </Button>
                                ))}
                            </div>
                        </ScrollArea>
                    </div>
                )}
            </div>

            {/* MAIN CONTENT AREA */}
            <div className="flex-1 flex flex-col h-full bg-background min-w-0">
                {/* Header & Controls */}
                <div className="flex flex-col gap-2 p-4 border-b border-border/40 bg-background/50">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <h3 className="font-semibold text-lg">
                                {getHeaderTitle()}
                                <span className="ml-2 text-xs font-normal text-muted-foreground bg-muted px-2 py-0.5 rounded-full">{sortedTodos.length}</span>
                            </h3>

                            <div className="flex bg-muted/50 p-0.5 rounded-lg border ml-4">
                                <Button variant={view === 'list' ? 'secondary' : 'ghost'} size="sm" className="h-6 px-2 text-xs" onClick={() => setView('list')}>
                                    <ListIcon className="w-3.5 h-3.5 mr-1" /> {t('todos.list')}
                                </Button>
                                <Button variant={view === 'calendar' ? 'secondary' : 'ghost'} size="sm" className="h-6 px-2 text-xs" onClick={() => setView('calendar')}>
                                    <LayoutGrid className="w-3.5 h-3.5 mr-1" /> {t('todos.calendar')}
                                </Button>
                            </div>
                        </div>

                        <div className="flex items-center gap-2">
                            <Select value={sortBy} onValueChange={(v: any) => setSortBy(v)}>
                                <SelectTrigger className="h-8 text-xs w-[110px]">
                                    <SortAsc className="w-3 h-3 mr-1" />
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="created">{t('todos.sort.newest')}</SelectItem>
                                    <SelectItem value="priority">{t('todos.sort.priority')}</SelectItem>
                                    <SelectItem value="date">{t('todos.sort.dueDate')}</SelectItem>
                                </SelectContent>
                            </Select>
                            <Button variant="ghost" size="icon" onClick={() => fetchTodos()} className="h-8 w-8" title={t('todos.refresh')}>
                                <span className="sr-only">{t('todos.refresh')}</span>
                                <svg width="12" height="12" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-3 h-3"><path d="M1.90321 7.29677C1.90321 10.341 4.36492 12.8095 7.40021 12.8095C9.6913 12.8095 11.6669 11.3932 12.5159 9.38972C12.5699 9.26229 12.7176 9.20211 12.845 9.25611C12.9724 9.31011 13.0326 9.45781 12.9786 9.58523C12.0232 11.8398 9.80053 13.4332 7.22383 13.4332C3.99222 13.4332 1.36979 10.8052 1.36979 7.56477C1.36979 4.32435 3.99222 1.69632 7.22383 1.69632C8.80801 1.69632 10.2452 2.32488 11.3094 3.3541L12.0626 2.60092C12.1867 2.47683 12.3896 2.47898 12.5111 2.60579C12.6326 2.7326 12.6288 2.93406 12.5026 3.05609L11.1666 4.34863C11.1042 4.40901 11.0206 4.44284 10.9338 4.44284H10.9332H8.97402C8.79974 4.44284 8.65844 4.30153 8.65844 4.12726C8.65844 3.95298 8.79974 3.81168 8.97402 3.81168H10.1584C9.25586 2.90999 8.03154 2.37897 6.69041 2.37897C4.16788 2.37897 2.11364 4.43321 2.11364 6.96577Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd"></path></svg>
                            </Button>
                        </div>
                    </div>

                    {/* Creation Form */}
                    <form onSubmit={handleCreateTodo} className="flex flex-col gap-2 pt-2">
                        <div className="flex gap-2">
                            <Input
                                placeholder={t('todos.create.placeholder')}
                                value={newTitle}
                                onChange={(e) => setNewTitle(e.target.value)}
                                className="h-9 text-sm flex-1"
                                disabled={isCreating}
                            />
                            <Button type="submit" size="sm" className="h-9 px-3" disabled={!newTitle.trim() || isCreating}>
                                <Plus className="h-4 w-4 mr-1" /> {t('todos.create.add')}
                            </Button>
                        </div>
                        <div className="flex gap-2 items-center">
                            <Select value={newPriority} onValueChange={(v: any) => setNewPriority(v)}>
                                <SelectTrigger className="h-7 w-[100px] text-xs">
                                    <SelectValue placeholder={t('todos.create.priorityPlaceholder')} />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="low">{t('todos.priority.low')}</SelectItem>
                                    <SelectItem value="medium">{t('todos.priority.medium')}</SelectItem>
                                    <SelectItem value="high">{t('todos.priority.high')}</SelectItem>
                                </SelectContent>
                            </Select>

                            <Input
                                placeholder={t('todos.create.categoryPlaceholder')}
                                value={newCategory}
                                onChange={(e) => setNewCategory(e.target.value)}
                                className="h-7 text-xs w-[120px]"
                            />

                            <Popover>
                                <PopoverTrigger asChild>
                                    <Button variant="outline" size="sm" className={cn("h-7 text-xs justify-start text-left font-normal", !newDueDate && "text-muted-foreground", "w-[130px]")}>
                                        <CalendarIcon className="mr-1 h-3 w-3" />
                                        {newDueDate ? format(newDueDate, "PPP", { locale: getDateLocale() }) : t('todos.create.setDate')}
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-auto p-0" align="start">
                                    <Calendar
                                        mode="single"
                                        selected={newDueDate}
                                        onSelect={setNewDueDate}
                                        initialFocus
                                    />
                                </PopoverContent>
                            </Popover>
                        </div>
                    </form>
                </div>

                {/* Content */}
                <ScrollArea className="flex-1">
                    {loading && todos.length === 0 ? (
                        <div className="p-8 text-center text-sm text-muted-foreground">{t('todos.empty.loading')}</div>
                    ) : view === 'list' ? (
                        <div className="p-2 space-y-2">
                            {sortedTodos.length === 0 ? (
                                <div className="text-center text-xs text-muted-foreground py-10">
                                    {statusFilter !== 'all' || priorityFilter !== 'all' || categoryFilter ? t('todos.empty.noFilterMatch') : t('todos.empty.noActive')}
                                </div>
                            ) : (
                                sortedTodos.map(todo => (
                                    <div key={todo.id} className={cn(
                                        "group flex items-start gap-2 p-3 rounded-lg border text-sm transition-all hover:bg-accent/50 hover:shadow-sm bg-card",
                                        todo.status === 'completed' as TodoStatus ? "opacity-60 bg-accent/20" : ""
                                    )}>
                                        <button
                                            onClick={() => handleStatusChange(todo.id, todo.status)}
                                            className={cn(
                                                "mt-0.5 h-4 w-4 rounded-sm border flex items-center justify-center transition-colors shrink-0",
                                                todo.status === 'completed' as TodoStatus ? "bg-primary border-primary text-primary-foreground" : "border-muted-foreground/40 hover:border-primary"
                                            )}
                                        >
                                            {todo.status === 'completed' as TodoStatus && <Check className="h-3 w-3" />}
                                        </button>

                                        <div className="flex-1 min-w-0 grid gap-1.5">
                                            <div className="flex items-center gap-2">
                                                <span className={cn(
                                                    "font-medium truncate leading-none",
                                                    todo.status === 'completed' as TodoStatus && "line-through text-muted-foreground"
                                                )}>
                                                    {todo.title}
                                                </span>
                                                {/* @ts-ignore category check */}
                                                {todo.category && (
                                                    <span className="text-[10px] bg-secondary px-1.5 py-0.5 rounded text-muted-foreground">
                                                        {/* @ts-ignore */}
                                                        {todo.category}
                                                    </span>
                                                )}
                                                {/* @ts-ignore source check */}
                                                {(todo as any).source_conversation_id && (
                                                    <Link
                                                        to="/chat"
                                                        search={{ threadId: (todo as any).source_conversation_id }}
                                                        className="ml-auto"
                                                    >
                                                        <Button size="icon" variant="ghost" className="h-5 w-5 text-muted-foreground hover:text-primary" title={t('todos.jumpToChat')}>
                                                            <MessageSquare className="h-3 w-3" />
                                                        </Button>
                                                    </Link>
                                                )}

                                                <Link
                                                    to="/chat"
                                                    search={{
                                                        // @ts-ignore
                                                        thread_id: (todo as any).source_conversation_id,
                                                        message: `${t('todos.executeTaskPrefix')}${todo.title}\n${todo.description || ''}`,
                                                        autoSend: "true",
                                                        quoteId: (todo as any).source_message_id
                                                    }}
                                                    className={cn("ml-1", !(todo as any).source_conversation_id && "ml-auto")}
                                                >
                                                    <Button size="icon" variant="ghost" className="h-5 w-5 text-muted-foreground hover:text-yellow-500" title={t('todos.execute')}>
                                                        <Zap className="h-3 w-3" fill="currentColor" />
                                                    </Button>
                                                </Link>
                                            </div>

                                            {todo.description && (
                                                <p className="text-xs text-muted-foreground line-clamp-2">{todo.description}</p>
                                            )}

                                            <div className="flex items-center gap-2">
                                                <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full border capitalize", getPriorityColor(todo.priority))}>
                                                    {t('todos.priority.' + todo.priority)}
                                                </span>
                                                {todo.due_date && (
                                                    <span className={cn("flex items-center text-[10px]",
                                                        new Date(todo.due_date) < new Date() && todo.status !== 'completed' as TodoStatus ? "text-red-500 font-medium" : "text-muted-foreground"
                                                    )}>
                                                        <CalendarIcon className="h-3 w-3 mr-1" />
                                                        {formatDueDate(todo.due_date)}
                                                    </span>
                                                )}
                                            </div>
                                        </div>

                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity text-destructive hover:text-destructive hover:bg-destructive/10"
                                            onClick={() => handleDelete(todo.id)}
                                        >
                                            <Trash2 className="h-3 w-3" />
                                        </Button>
                                    </div>
                                ))
                            )}
                        </div>
                    ) : (
                        renderCalendarView()
                    )}
                </ScrollArea>
            </div >
        </div >
    )
}
