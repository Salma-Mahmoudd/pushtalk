import { createBrowserRouter, Navigate } from 'react-router'

import { AuthPage } from '@/features/auth/components/auth-page'
import { GuestOnly, RequireAuth } from '@/features/auth/components/guards'
import { ChannelsPage } from '@/features/channels/channels-page'

import { AppShell } from './app-shell'

export const router = createBrowserRouter([
  {
    element: <GuestOnly />,
    children: [
      { path: '/login', element: <AuthPage mode="login" /> },
      { path: '/signup', element: <AuthPage mode="signup" /> },
    ],
  },
  {
    element: <RequireAuth />,
    children: [{ element: <AppShell />, children: [{ path: '/channels', element: <ChannelsPage /> }] }],
  },
  { path: '*', element: <Navigate to="/channels" replace /> },
])
