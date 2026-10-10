import { Avatar, AvatarBadge, AvatarFallback } from '@/shared/ui/avatar'

import type { Member } from '../api'

export function MemberList({ members, online }: { members: Member[]; online: ReadonlySet<string> }) {
  const sorted = [...members].sort((a, b) => Number(online.has(b.id)) - Number(online.has(a.id)))

  return (
    <ul className="grid gap-1" aria-label="Members">
      {sorted.map((member) => {
        const isOnline = online.has(member.id)
        return (
          <li key={member.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5">
            <Avatar className="size-7">
              <AvatarFallback className="text-xs">{member.username.slice(0, 2).toUpperCase()}</AvatarFallback>
              <AvatarBadge className={isOnline ? 'bg-green-500' : 'bg-muted-foreground/40'} />
            </Avatar>
            <span className="truncate text-sm">{member.username}</span>
            <span className="sr-only">{isOnline ? 'online' : 'offline'}</span>
          </li>
        )
      })}
    </ul>
  )
}
