import { Outlet } from 'react-router'

/** Sign-in, registration and "awaiting approval": what the product does, then the form. */
export function AuthLayout() {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section className="flex flex-col justify-between bg-sidebar px-6 py-8 sm:px-12 lg:py-14">
        <p className="text-[1.15rem] font-extrabold tracking-tight">
          FindMy<span className="text-primary">Jobs</span>
        </p>
        <div className="my-10 max-w-[30rem] lg:my-0">
          <h1 className="text-[2.1rem] font-bold leading-[1.1] tracking-tight sm:text-[2.75rem]">
            Find the jobs that fit you, and apply without the busywork.
          </h1>
          <ul className="mt-8 hidden space-y-3 text-[0.975rem] text-muted-foreground lg:block">
            <li>Every job is scored against your resume, so you see the good fits first.</li>
            <li>Recruiter contacts come from public hiring posts, with the post as proof.</li>
            <li>
              Emails, resumes and cover letters are drafted for you — nothing is sent until you
              approve it.
            </li>
          </ul>
        </div>
        <span aria-hidden="true" />
      </section>
      <main className="flex items-start justify-center px-4 py-10 lg:items-center">
        <div className="w-full max-w-sm">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
