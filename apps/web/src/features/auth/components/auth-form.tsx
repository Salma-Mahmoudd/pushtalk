import { AlertCircleIcon } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'

import { Logo } from '@/shared/brand/logo'
import { ApiError } from '@/shared/lib/api/client'
import { Alert, AlertDescription } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/shared/ui/field'
import { Input } from '@/shared/ui/input'
import { Spinner } from '@/shared/ui/spinner'

import { authApi } from '../api'
import { startSession } from '../session'

type Mode = 'login' | 'signup'

const COPY = {
  login: {
    title: 'Welcome back',
    description: 'Log in to talk in your channels.',
    submit: 'Log in',
    switchText: 'New to PushTalk?',
    switchLink: 'Create an account',
    switchTo: '/signup',
  },
  signup: {
    title: 'Create your account',
    description: 'Pick a username and start talking.',
    submit: 'Sign up',
    switchText: 'Already have an account?',
    switchLink: 'Log in',
    switchTo: '/login',
  },
} as const

/** Message shown above the form for errors that are not about one field. */
function formMessage(error: ApiError): string | null {
  switch (error.code) {
    case 'validation_error':
    case 'username_taken':
      return null
    case 'rate_limited':
      return `Too many attempts. Try again in ${error.retryAfter ?? 60} s.`
    case 'network_error':
      return 'PushTalk cannot be reached. Check the connection and try again.'
    default:
      return error.status >= 500 ? 'Something went wrong. Please try again.' : error.message
  }
}

export function AuthForm({ mode }: { mode: Mode }) {
  const copy = COPY[mode]
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const credentials = { username: String(form.get('username')), password: String(form.get('password')) }
    setPending(true)
    setError(null)
    try {
      // The route guard redirects once the session is stored.
      startSession(await (mode === 'login' ? authApi.login(credentials) : authApi.signup(credentials)))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, null, null))
      setPending(false)
    }
  }

  const usernameError = error?.code === 'username_taken' ? error.message : error?.fieldMessage('username')
  const passwordError = error?.fieldMessage('password')
  const message = error ? formMessage(error) : null

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="items-center text-center">
        <Logo className="mb-2 text-lg" />
        <CardTitle className="text-2xl">{copy.title}</CardTitle>
        <CardDescription>{copy.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit}>
          <FieldGroup>
            {message && (
              <Alert variant="destructive" role="alert">
                <AlertCircleIcon />
                <AlertDescription>{message}</AlertDescription>
              </Alert>
            )}
            <Field data-invalid={Boolean(usernameError)}>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                autoFocus
                aria-invalid={Boolean(usernameError)}
                {...(mode === 'signup' && { pattern: '[A-Za-z0-9_]{3,32}', maxLength: 32 })}
              />
              {mode === 'signup' && <FieldDescription>3–32 letters, digits or underscores.</FieldDescription>}
              <FieldError>{usernameError}</FieldError>
            </Field>
            <Field data-invalid={Boolean(passwordError)}>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                required
                maxLength={128}
                aria-invalid={Boolean(passwordError)}
                {...(mode === 'signup' && { minLength: 8 })}
              />
              {mode === 'signup' && <FieldDescription>At least 8 characters.</FieldDescription>}
              <FieldError>{passwordError}</FieldError>
            </Field>
            <Button type="submit" disabled={pending}>
              {pending && <Spinner />}
              {copy.submit}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              {copy.switchText}{' '}
              <Link to={copy.switchTo} className="font-medium text-primary underline-offset-4 hover:underline">
                {copy.switchLink}
              </Link>
            </p>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  )
}
