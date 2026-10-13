import { Link } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { AutomationCard } from '@/features/outreach/components/AutomationCard'

/** Phase 20: run the apply pipeline (its settings live in Settings). */
export default function AutomationPipelinePage() {
  return (
    <>
      <PageHeader
        title="Apply pipeline"
        description="Scores jobs, prepares resumes and cover letters, and drafts the emails. Drafts wait in Outreach › Outbox for your approval."
        actions={
          <Link to="/settings" className="text-sm text-primary hover:underline">
            Pipeline settings →
          </Link>
        }
      />
      <AutomationCard />
    </>
  )
}
