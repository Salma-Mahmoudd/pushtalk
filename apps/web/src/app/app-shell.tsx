import { LogOutIcon } from 'lucide-react'
import { Outlet } from 'react-router'

import { logout } from '@/features/auth/session'
import { useAuthStore } from '@/features/auth/store'
import { Logo } from '@/shared/brand/logo'
import { ModeToggle } from '@/shared/theme/mode-toggle'
import { Button } from '@/shared/ui/button'

/** Layout of every logged-in page: header with user and actions, page below. */
export function AppShell() {
  const username = useAuthStore((state) => state.user?.username)

  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex items-center gap-2 border-b px-4 py-2">
        <Logo />
        <span className="ms-auto text-sm text-muted-foreground">{username}</span>
        <ModeToggle />
        <Button variant="ghost" size="icon" aria-label="Log out" onClick={() => void logout()}>
          <LogOutIcon />
        </Button>
      </header>
      <Outlet />
    </div>
  )
}
