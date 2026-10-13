import { PageHeader } from '@/components/common/PageHeader'
import { DigestCard } from '@/features/hunt/components/DigestCard'

/** Phase 20: today's digest (its settings live in Settings). */
export default function DigestPage() {
  return (
    <>
      <PageHeader
        title="Daily digest"
        description="Your best new matches every morning, on Home and by email."
      />
      <div className="max-w-3xl">
        <DigestCard />
      </div>
    </>
  )
}
