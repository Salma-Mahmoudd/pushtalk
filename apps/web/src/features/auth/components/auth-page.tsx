import { ModeToggle } from '@/shared/theme/mode-toggle'

import { AuthForm } from './auth-form'

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  return (
    <main className="relative grid min-h-svh place-items-center p-4">
      <div className="absolute end-4 top-4">
        <ModeToggle />
      </div>
      <AuthForm mode={mode} />
    </main>
  )
}
