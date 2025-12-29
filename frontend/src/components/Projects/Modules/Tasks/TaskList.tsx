import React, { useEffect, useState } from 'react'
import { useParams } from '@tanstack/react-router'
import { TasksService } from '@/client'
import { Task, TaskPriority, TaskStatus } from '@/types/task'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Loader2, Plus, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

export const TaskList: React.FC = () => {
    const { projectId } = useParams({ from: '/_layout/projects/$projectId' })
    const { t } = useTranslation()
    const [tasks, setTasks] = useState<Task[]>([])
    const [isLoading, setIsLoading] = useState(false)

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
            toast.error(t('Task.FailedToLoad'))
        } finally {
            setIsLoading(false)
        }
    }

    useEffect(() => {
        fetchTasks()
    }, [projectId])

    const getStatusColor = (status: number) => {
        switch (status) {
            case TaskStatus.PENDING: return 'bg-gray-200 text-gray-700'
            case TaskStatus.IN_PROGRESS: return 'bg-blue-100 text-blue-700'
            case TaskStatus.COMPLETED: return 'bg-green-100 text-green-700'
            default: return 'bg-gray-100 text-gray-600'
        }
    }

    const getStatusLabel = (status: number) => {
        // Should use translation keys usually
        switch (status) {
            case TaskStatus.PENDING: return 'Pending'
            case TaskStatus.IN_PROGRESS: return 'In Progress'
            case TaskStatus.COMPLETED: return 'Done'
            default: return 'Unknown'
        }
    }

    const getPriorityLabel = (p: number) => {
        switch (p) {
            case TaskPriority.URGENT: return 'Urgent'
            case TaskPriority.HIGH: return 'High'
            case TaskPriority.NORMAL: return 'Normal'
            case TaskPriority.LOW: return 'Low'
            default: return 'Normal'
        }
    }

    return (
        <div className="h-full w-full overflow-auto p-6 space-y-6">
            <div className="space-y-4">
                <div className="flex justify-between items-center">
                    <h2 className="text-xl font-semibold tracking-tight">Tasks</h2>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" onClick={fetchTasks} disabled={isLoading}>
                            <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                            Refresh
                        </Button>
                        <Button size="sm">
                            <Plus className="w-4 h-4 mr-2" />
                            Create Task
                        </Button>
                    </div>
                </div>

                <Card>
                    <CardContent className="p-0">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[100px]">ID</TableHead>
                                    <TableHead>Title</TableHead>
                                    <TableHead>AI Score</TableHead>
                                    <TableHead>Priority</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead>Progress</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {isLoading && tasks.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={6} className="h-24 text-center">
                                            <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
                                        </TableCell>
                                    </TableRow>
                                ) : tasks.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                                            No tasks found.
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    tasks.map((task) => (
                                        <TableRow key={task.task_id} className="cursor-pointer hover:bg-muted/50">
                                            <TableCell className="font-medium">#{task.task_id}</TableCell>
                                            <TableCell>
                                                <div className="font-medium">{task.task_title}</div>
                                                {task.task_desc && (
                                                    <div className="text-xs text-muted-foreground line-clamp-1">{task.task_desc}</div>
                                                )}
                                            </TableCell>
                                            <TableCell>
                                                {task.match_score !== undefined && (
                                                    <Badge variant={task.match_score > 80 ? 'default' : 'secondary'}>
                                                        {task.match_score}%
                                                    </Badge>
                                                )}
                                            </TableCell>
                                            <TableCell>
                                                <span className="text-sm text-muted-foreground">{getPriorityLabel(task.priority)}</span>
                                            </TableCell>
                                            <TableCell>
                                                <Badge className={getStatusColor(task.status)} variant="outline">
                                                    {getStatusLabel(task.status)}
                                                </Badge>
                                            </TableCell>
                                            <TableCell>
                                                <div className="w-[60px] bg-secondary h-2 rounded-full overflow-hidden">
                                                    <div
                                                        className="bg-primary h-full transition-all"
                                                        style={{ width: `${task.progress || 0}%` }}
                                                    />
                                                </div>
                                                <div className="text-xs text-muted-foreground mt-1">{task.progress || 0}%</div>
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
