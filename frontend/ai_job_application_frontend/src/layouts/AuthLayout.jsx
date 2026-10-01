import { BriefcaseBusiness } from 'lucide-react'
import { Outlet } from 'react-router'

/** Centered card layout for sign-in, registration and "awaiting approval". */
export function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-10">
      <div className="flex items-center gap-2 text-lg font-semibold">
        <BriefcaseBusiness className="size-6 text-primary" aria-hidden="true" />
        AI Job Assistant
      </div>
      <div className="w-full max-w-sm">
        <Outlet />
      </div>
    </div>
  )
}
