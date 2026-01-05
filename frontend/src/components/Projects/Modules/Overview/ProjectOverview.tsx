import React, { useEffect, useState } from 'react'
import { useParams, Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
    Activity, Users, Clock,
    CheckCircle2, CheckSquare, RefreshCw, ListTodo
} from "lucide-react"
import { ProjectModulesService, TasksService } from "@/client/sdk.gen"
import { useProjectStore } from "@/stores/projectStore"
// import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

interface ProjectStats {
    total_tasks: number
    completed_tasks: number
    active_tasks: number
    pending_tasks: number
    members_count: number
}

interface RecentTask {
    task_id: number
    task_title: string
    status: number
    priority: number
    update_time_format: string
}

export const ProjectOverview: React.FC = () => {
    const { projectId } = useParams({ from: '/_layout/projects/$projectId' })
    const { currentProject } = useProjectStore()
    const { t } = useTranslation()
    const [stats, setStats] = useState<ProjectStats | null>(null)
    // const [members, setMembers] = useState<ProjectMember[]>([])
    const [recentTasks, setRecentTasks] = useState<RecentTask[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const loadData = async () => {
            if (!projectId) return
            setLoading(true)
            try {
                const token = localStorage.getItem('access_token')
                // Fetch stats
                const statsData = await ProjectModulesService.getProjectStatistics({
                    projectId: parseInt(projectId),
                    authorization: token
                }) as any
                if (statsData.code === 0) {
                    setStats(statsData.data)
                }

                // Fetch tasks for recent activity
                const tasksData = await TasksService.getProjectTasks({
                    projectId: parseInt(projectId),
                    page: 1,
                    pageSize: 5,
                    authorization: token
                }) as any
                if (tasksData.code === 0) {
                    setRecentTasks(tasksData.data.list || [])
                }

                // Fetch Project Detail for members (using ProjectModulesService or ProjectsService?)
                // Assuming we can get members from project detail or stats
                // For now, let's look at what we have. 
                // The mobile app gets members from project detail. 
                // Let's defer members fetching or try to use a service if available.
                // We'll leave members empty for now if not easily available, or check ProjectsService

            } catch (error) {
                console.error("Failed to load overview data", error)
            } finally {
                setLoading(false)
            }
        }
        loadData()
    }, [projectId])

    if (loading) {
        return <div className="p-6">Loading...</div>
    }

    return (
        <div className="h-full w-full overflow-auto p-6 space-y-6">
            <div className="flex justify-between items-center">
                <div className="flex items-center gap-3">
                    <h2 className="text-2xl font-bold tracking-tight">{t('projects.overview.title', 'Project Overview')}</h2>
                    {/* Status Badges */}
                    {currentProject?.indexing_status === 'indexing' && (
                        <Badge variant="secondary" className="bg-blue-100 text-blue-700 gap-1">
                            <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Indexing
                        </Badge>
                    )}
                    {(currentProject?.summarization_status === 'running' || currentProject?.summarization_status === 'SUMMARIZING') && (
                        <Badge variant="secondary" className="bg-purple-100 text-purple-700 gap-1">
                            <ListTodo className="h-3.5 w-3.5 animate-pulse" /> Analyzing
                        </Badge>
                    )}
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            {t('projects.stats.totalTasks', 'Total Tasks')}
                        </CardTitle>
                        <Activity className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats?.total_tasks || 0}</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            {t('projects.stats.completed', 'Completed')}
                        </CardTitle>
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats?.completed_tasks || 0}</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            {t('projects.stats.inProgress', 'In Progress')}
                        </CardTitle>
                        <Clock className="h-4 w-4 text-blue-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats?.active_tasks || 0}</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            {t('projects.stats.members', 'Members')}
                        </CardTitle>
                        <Users className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats?.members_count || 0}</div>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                {/* Recent Activity */}
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>{t('projects.overview.recentActivity', 'Recent Activity')}</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {recentTasks.length === 0 ? (
                                <div className="text-center text-sm text-muted-foreground py-4">
                                    {t('projects.overview.noActivity', 'No recent activity')}
                                </div>
                            ) : (
                                recentTasks.map((task) => (
                                    <div key={task.task_id} className="flex items-center justify-between border-b last:border-0 pb-2 last:pb-0">
                                        <div className="space-y-1">
                                            <p className="text-sm font-medium leading-none">{task.task_title}</p>
                                            <p className="text-xs text-muted-foreground">{task.update_time_format}</p>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Badge variant={task.status === 2 ? "default" : "secondary"}>
                                                {task.status === 2 ? 'In Progress' : task.status === 3 ? 'Done' : 'Pending'}
                                            </Badge>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </CardContent>
                </Card>

                {/* Quick Actions / Members */}
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>{t('projects.overview.quickActions', 'Quick Actions')}</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        <Link to={`/projects/${projectId}/tasks`} className="block">
                            <Button variant="outline" className="w-full justify-start">
                                <CheckSquare className="mr-2 h-4 w-4" />
                                {t('projects.actions.viewTasks', 'View Tasks')}
                            </Button>
                        </Link>
                        <Link to={`/projects/${projectId}/gantt`} className="block">
                            <Button variant="outline" className="w-full justify-start">
                                <Activity className="mr-2 h-4 w-4" />
                                {t('projects.actions.viewGantt', 'View Gantt Chart')}
                            </Button>
                        </Link>
                        <Link to={`/projects/${projectId}/timesheet`} className="block">
                            <Button variant="outline" className="w-full justify-start">
                                <Clock className="mr-2 h-4 w-4" />
                                {t('projects.actions.logTime', 'Log Time')}
                            </Button>
                        </Link>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
