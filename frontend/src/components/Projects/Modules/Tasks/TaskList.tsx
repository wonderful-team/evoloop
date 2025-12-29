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

export const TaskList: React.FC = () => {
    const { projectId } = useParams({ from: '/_layout/projects/$projectId' })
    const { t } = useTranslation()
    const [tasks, setTasks] = useState<Task[]>([])
    const [isLoading, setIsLoading] = useState(false)

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
                    <DataTable columns={columns} data={tasks} />
                </div>
            </div>
        </div>
    )
}
