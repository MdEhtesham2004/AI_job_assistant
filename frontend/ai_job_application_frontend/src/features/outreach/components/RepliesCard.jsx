import { MessageSquareReply } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDateTime } from '@/lib/format'

import { REPLY_CATEGORY, REPLY_TARGET } from '../api'
import { useConfirmReply, useReplies } from '../hooks'

/** Application page: replies found in the Gmail thread (checked every 5 minutes). */
export function RepliesCard({ applicationId }) {
  const replies = useReplies(applicationId).data ?? []
  const confirm = useConfirmReply()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageSquareReply className="size-4 text-primary" aria-hidden="true" />
          Replies
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {replies.length === 0 && (
          <p className="text-muted-foreground">
            No reply yet. Gmail is checked every 5 minutes; the status updates by itself.
          </p>
        )}
        {replies.map((reply) => {
          const reading = reply.classification
          const style = reading ? REPLY_CATEGORY[reading.category] : null
          const ask =
            reading &&
            !reading.applied_transition &&
            reading.user_confirmed === null &&
            REPLY_TARGET[reading.category]
          return (
            <article key={reply.id} className="rounded-md border p-3">
              <p className="flex flex-wrap items-center gap-2">
                {reply.status === 'bounced' ? (
                  <Badge variant="destructive">Bounced</Badge>
                ) : (
                  style && <Badge variant={style.variant}>{style.label}</Badge>
                )}
                {reading && (
                  <span className="text-xs text-muted-foreground">
                    {Math.round(reading.confidence * 100)}% sure
                    {reading.applied_transition ? ' · status updated' : ''}
                  </span>
                )}
                <span className="text-xs text-muted-foreground">
                  {reply.from_address} · {formatDateTime(reply.received_at)}
                </span>
              </p>
              {reading && <p className="mt-1">{reading.summary}</p>}
              {reading?.suggested_action && (
                <p className="mt-1 text-xs">
                  <span className="text-muted-foreground">Suggested:</span>{' '}
                  {reading.suggested_action}
                </p>
              )}
              {ask && (
                <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md bg-warning/10 p-2">
                  <span className="text-xs">
                    Not sure — set the status to <span className="font-medium">{ask}</span>?
                  </span>
                  <Button
                    size="sm"
                    disabled={confirm.isPending}
                    onClick={() => confirm.mutate({ id: reading.id, accept: true })}
                  >
                    Yes, set to {ask}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={confirm.isPending}
                    onClick={() => confirm.mutate({ id: reading.id, accept: false })}
                  >
                    No
                  </Button>
                </div>
              )}
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-muted-foreground">
                  Show the email
                </summary>
                <p className="mt-1 whitespace-pre-wrap text-xs">{reply.body_text}</p>
              </details>
            </article>
          )
        })}
      </CardContent>
    </Card>
  )
}
