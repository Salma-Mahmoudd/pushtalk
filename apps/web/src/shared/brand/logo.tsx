import { cn } from 'cn'

/** The app mark next to the "PushTalk" wordmark. */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 font-bold', className)}>
      <img src="/favicon.svg" alt="" className="size-7" />
      PushTalk
    </span>
  )
}
