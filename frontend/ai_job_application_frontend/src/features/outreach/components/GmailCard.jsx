import { Mail } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDateTime } from '@/lib/format'

import { useConnectGmail, useDisconnectGmail, useGmailStatus } from '../hooks'

/** Settings: connect the Gmail account applications are sent from. */
export function GmailCard() {
  const status = useGmailStatus()
  const connect = useConnectGmail()
  const disconnect = useDisconnectGmail()
  const gmail = status.data

  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="size-4 text-primary" aria-hidden="true" />
          Gmail
        </CardTitle>
        <CardDescription>
          Applications are sent from your own Gmail — only after you approve each email.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {status.isPending && <p className="text-muted-foreground">Loading…</p>}
        {gmail && !gmail.configured && !gmail.connected && (
          <p className="text-muted-foreground">
            Gmail is not set up on the server yet (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and
            TOKEN_ENCRYPTION_KEY in the backend .env).
          </p>
        )}
        {gmail?.connected && (
          <>
            <p>
              Connected as <span className="font-medium">{gmail.account_email}</span>
              {gmail.connected_at && (
                <span className="text-muted-foreground">
                  {' '}
                  · since {formatDateTime(gmail.connected_at)}
                </span>
              )}
            </p>
            <div className="flex flex-wrap gap-1.5">
              <Badge variant={gmail.can_send ? 'success' : 'destructive'}>
                {gmail.can_send ? 'Can send' : 'Cannot send'}
              </Badge>
              <Badge variant={gmail.can_read ? 'success' : 'outline'}>
                {gmail.can_read ? 'Can read replies' : 'No read access'}
              </Badge>
            </div>
            <Button
              variant="outline"
              onClick={() => disconnect.mutate()}
              disabled={disconnect.isPending}
            >
              Disconnect
            </Button>
          </>
        )}
        {gmail && !gmail.connected && gmail.configured && (
          <>
            {gmail.status && (
              <p className="text-destructive">
                {gmail.account_email}: Google no longer accepts the saved access — reconnect.
              </p>
            )}
            <Button onClick={() => connect.mutate()} disabled={connect.isPending}>
              <Mail />
              {gmail.status ? 'Reconnect Gmail' : 'Connect Gmail'}
            </Button>
            <p className="text-xs text-muted-foreground">
              Google asks for permission to send email and to read replies (used from the next phase
              to track answers). You can disconnect at any time.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
