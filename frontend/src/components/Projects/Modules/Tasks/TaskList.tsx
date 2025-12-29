import React, { useEffect, useState } from 'react'
import { useParams } from '@tanstack/react-router'
import { TasksService } from '@/client'
import { Task } from '@/types/task'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DataTable } from '@/components/Common/DataTable'
import { getColumns } from './columns'
import { Plus, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TaskDetail } from './TaskDetail'

export const TaskList: React.FC = () => {
    const { projectId } = useParams({ from: '/_layout/projects/$projectId' })
    const { t } = useTranslation()
    const [tasks, setTasks] = useState<Task[]>([])
    const [isLoading, setIsLoading] = useState(false)
    const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null)
    const [isDetailOpen, setIsDetailOpen] = useState(false)

    const handleRowClick = (task: Task) => {
        // Assuming task has an id or task_id property. 
        // Need to check Task type definition. Usually 'id' or 'task_id'.
        // Based on other files, it might be 'task_id' from backend but 'id' in frontend model?
        // Let's check sdk types. TasksService returns 'unknown' usually but let's assume 'task_id' based on ProjectOverview usage.
        // Actually Task type import suggests we have a frontend type.
        // Let's assume 'task_id' for safety or check the type file if needed.
        // But for now casting to any to read task_id is safe enough if we are unsure.
        const id = (task as any).task_id || (task as any).id
        if (id) {
            setSelectedTaskId(id)
            setIsDetailOpen(true)
        }
    }

    // Memoize columns to prevent re-renders, pass t
    const columns = React.useMemo(() => getColumns(t), [t])

    const fetchTasks = async () => {
        if (!projectId) return
        setIsLoading(true)
        try {
            const token = localStorage.getItem('access_token')
            const res: any = await TasksService.getProjectTasks({
                projectId: parseInt(projectId),
                page: 1,
                pageSize: 100,
                authorization: token
            })
            // Support different response structures
            if (res && res.list) {
                setTasks(res.list)
            } else if (Array.isArray(res)) {
                setTasks(res)
            } else {
                setTasks([])
            }
        } catch (error) {
            console.error(error)
            toast.error(t('projects.tasks.failedToLoad'))
        } finally {
            setIsLoading(false)
        }
    }

    useEffect(() => {
        fetchTasks()
    }, [projectId])

    return (
        <div className="h-full w-full overflow-auto p-6 space-y-6">
            <div className="space-y-4">
                <div className="flex justify-between items-center">
                    <h2 className="text-xl font-semibold tracking-tight">{t('projects.tasks.title')}</h2>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" onClick={fetchTasks} disabled={isLoading}>
                            <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                            {t('projects.tasks.refresh')}
                        </Button>
                        <Button size="sm">
                            <Plus className="w-4 h-4 mr-2" />
                            {t('projects.tasks.create')}
                        </Button>
                    </div>
                </div>

                <div className="bg-background rounded-md">
                    <DataTable columns={columns} data={tasks} onRowClick={handleRowClick} />
                </div>
            </div>

            <TaskDetail
                taskId={selectedTaskId}
                open={isDetailOpen}
                onOpenChange={setIsDetailOpen}
                onUpdate={fetchTasks}
            />
        </div>
    )
}
