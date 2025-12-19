import { createFileRoute } from '@tanstack/react-router'
import { ChatInterface } from '@/components/Chat/ChatInterface'

export const Route = createFileRoute('/_layout/chat')({
    component: ChatInterface,
})
