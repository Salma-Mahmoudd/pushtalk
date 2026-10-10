import { LogOutIcon } from 'lucide-react'
import { Outlet } from 'react-router'

import { logout } from '@/features/auth/session'
import { useAuthStore } from '@/features/auth/store'
import { ChannelSidebar } from '@/features/channels/components/channel-sidebar'
import { DirectList } from '@/features/directs/components/direct-list'
import { useUserSocket } from '@/features/directs/use-user-socket'
import { ModeToggle } from '@/shared/theme/mode-toggle'
import { Button } from '@/shared/ui/button'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/shared/ui/sidebar'

/** Layout of every logged-in page: sidebar (channels, direct messages), header, page. */
export function AppShell() {
  const username = useAuthStore((state) => state.user?.username)
  useUserSocket()

  return (
    <SidebarProvider>
      <ChannelSidebar>
        <DirectList />
      </ChannelSidebar>
      <SidebarInset className="flex h-svh flex-col">
        <header className="flex items-center gap-2 border-b px-2 py-2">
          <SidebarTrigger />
          <span className="ms-auto text-sm text-muted-foreground">{username}</span>
          <ModeToggle />
          <Button variant="ghost" size="icon" aria-label="Log out" onClick={() => void logout()}>
            <LogOutIcon />
          </Button>
        </header>
        <main className="flex min-h-0 flex-1 flex-col">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
