import { RefreshCw } from 'lucide-react'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ServiceRow } from '@/features/system/components/ServiceRow'
import { HEALTH_REFRESH_MS, useHealth } from '@/features/system/hooks/useHealth'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const CHECK_LABELS = { api: 'Backend API' }

function checkStatus(value) {
  return value === 'ok' ? 'healthy' : 'degraded'
}

export default function SystemStatusPage() {
  const { data, error, isPending, isFetching, refetch, dataUpdatedAt, errorUpdatedAt } = useHealth()

  const lastChecked = Math.max(dataUpdatedAt, errorUpdatedAt) || null

  return (
    <>
      <PageHeader
        title="System Status"
        description={`Live health of the platform services. Refreshes every ${HEALTH_REFRESH_MS / 1000} seconds.`}
        actions={
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={cn(isFetching && 'animate-spin')} />
            Refresh
          </Button>
        }
      />

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Services</CardTitle>
          <CardDescription>Last check: {formatDateTime(lastChecked)}</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {isPending && (
              <ServiceRow name="Backend API" status="checking" statusLabel="checking" />
            )}

            {error && (
              <ServiceRow
                name="Backend API"
                status="unreachable"
                statusLabel="unreachable"
                detail={error.message}
              />
            )}

            {data &&
              !error &&
              Object.entries(data.checks).map(([key, value]) => (
                <ServiceRow
                  key={key}
                  name={CHECK_LABELS[key] ?? key}
                  status={checkStatus(value)}
                  statusLabel={value === 'ok' ? 'healthy' : value}
                  detail={key === 'api' ? `v${data.version} · ${data.environment}` : undefined}
                />
              ))}
          </ul>

          {error?.requestId && (
            <p className="mt-3 text-xs text-muted-foreground">Request ID: {error.requestId}</p>
          )}
        </CardContent>
      </Card>
    </>
  )
}
