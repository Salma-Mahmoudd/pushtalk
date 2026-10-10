import { cn } from 'cn'
import { PlusIcon } from 'lucide-react'
import { NavLink } from 'react-router'

import {
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
} from '@/shared/ui/sidebar'

import { useDirects } from '../queries'
import { NewDirectDialog } from './new-direct-dialog'

/** Sidebar section: the user's one-to-one conversations, with the other person's online dot. */
export function DirectList() {
  const { data: directs, isPending } = useDirects()

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Direct messages</SidebarGroupLabel>
      <NewDirectDialog
        trigger={
          <SidebarGroupAction title="New direct message">
            <PlusIcon />
            <span className="sr-only">New direct message</span>
          </SidebarGroupAction>
        }
      />
      <SidebarGroupContent>
        <SidebarMenu>
          {isPending && (
            <SidebarMenuItem>
              <SidebarMenuSkeleton />
            </SidebarMenuItem>
          )}
          {directs?.map((direct) => (
            <SidebarMenuItem key={direct.id}>
              <NavLink to={`/channels/${direct.id}`}>
                {({ isActive }) => (
                  <SidebarMenuButton isActive={isActive}>
                    <span
                      className={cn('ms-1 size-2 shrink-0 rounded-full', direct.online ? 'bg-green-500' : 'bg-muted-foreground/40')}
                      aria-hidden="true"
                    />
                    <span className="truncate">{direct.peer.username}</span>
                    <span className="sr-only">{direct.online ? '(online)' : '(offline)'}</span>
                  </SidebarMenuButton>
                )}
              </NavLink>
            </SidebarMenuItem>
          ))}
          {!isPending && directs?.length === 0 && (
            <p className="px-2 py-1 text-xs text-muted-foreground">Press + to talk to one person.</p>
          )}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
