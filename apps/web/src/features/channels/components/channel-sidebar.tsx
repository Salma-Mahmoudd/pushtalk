import { CompassIcon, HashIcon, PlusIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router'

import { Logo } from '@/shared/brand/logo'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
} from '@/shared/ui/sidebar'

import { useChannels } from '../queries'
import { CreateChannelDialog } from './create-channel-dialog'

/** Navigation, the user's channels, then `children` (sections from other features). */
export function ChannelSidebar({ children }: { children?: ReactNode }) {
  const { data: channels, isPending } = useChannels()
  const joined = channels?.filter((channel) => channel.is_member) ?? []

  return (
    <Sidebar>
      <SidebarHeader className="px-4 py-3">
        <Logo />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <NavLink to="/channels" end>
                {({ isActive }) => (
                  <SidebarMenuButton isActive={isActive}>
                    <CompassIcon />
                    Browse channels
                  </SidebarMenuButton>
                )}
              </NavLink>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Your channels</SidebarGroupLabel>
          <CreateChannelDialog
            trigger={
              <SidebarGroupAction title="Create a channel">
                <PlusIcon />
                <span className="sr-only">Create a channel</span>
              </SidebarGroupAction>
            }
          />
          <SidebarGroupContent>
            <SidebarMenu>
              {isPending &&
                Array.from({ length: 3 }, (_, index) => (
                  <SidebarMenuItem key={index}>
                    <SidebarMenuSkeleton />
                  </SidebarMenuItem>
                ))}
              {joined.map((channel) => (
                <SidebarMenuItem key={channel.id}>
                  <NavLink to={`/channels/${channel.id}`}>
                    {({ isActive }) => (
                      <SidebarMenuButton isActive={isActive}>
                        <HashIcon />
                        <span className="truncate">{channel.name}</span>
                      </SidebarMenuButton>
                    )}
                  </NavLink>
                </SidebarMenuItem>
              ))}
              {!isPending && joined.length === 0 && (
                <p className="px-2 py-1 text-xs text-muted-foreground">Join or create a channel to start.</p>
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        {children}
      </SidebarContent>
    </Sidebar>
  )
}
