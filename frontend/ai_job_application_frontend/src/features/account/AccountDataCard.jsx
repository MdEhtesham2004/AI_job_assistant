import { useMutation } from '@tanstack/react-query'
import { Download, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { api } from '@/api/client'
import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/** Profile: download everything, or delete the account (password + email). */
export function AccountDataCard() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const exporter = useMutation({
    mutationFn: () => api.download('/users/me/export', 'my-data.zip'),
    onSuccess: (name) => toast.success(`Downloaded ${name}`),
    onError: (error) => toast.error(error.message),
  })
  const remover = useMutation({
    mutationFn: () =>
      api.post('/users/me/delete', { password, confirm_email: email }, { skipAuthRetry: true }),
    onSuccess: async () => {
      toast.success('Your account and all its data were deleted.')
      setOpen(false)
      await logout()
    },
  })

  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardTitle>Your data</CardTitle>
        <CardDescription>
          Download everything the platform stores about you, or delete your account.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => exporter.mutate()} disabled={exporter.isPending}>
          <Download />
          Export my data (ZIP)
        </Button>
        <Button variant="outline" className="text-destructive" onClick={() => setOpen(true)}>
          <Trash2 />
          Delete account
        </Button>
      </CardContent>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Delete your account?"
        description="This removes your resumes, jobs, applications, contacts, emails and files for good. Your Gmail access is revoked. This cannot be undone."
      >
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            remover.mutate()
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="delete-email">Type your email ({user?.email})</Label>
            <Input
              id="delete-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="delete-password">Password</Label>
            <Input
              id="delete-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {remover.isError && (
            <p role="alert" className="text-sm text-destructive">
              {remover.error.message}
            </p>
          )}
          <div className="flex gap-2">
            <Button
              type="submit"
              className="bg-destructive text-white hover:bg-destructive/90"
              disabled={!password || !email || remover.isPending}
            >
              Delete my account
            </Button>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </form>
      </Dialog>
    </Card>
  )
}
