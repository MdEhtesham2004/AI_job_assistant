import { AppLayout } from '@/layouts/AppLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import AdminUsersPage from '@/pages/admin/AdminUsersPage'
import AnalyticsPage from '@/pages/admin/AnalyticsPage'
import AuditLogPage from '@/pages/admin/AuditLogPage'
import ImportPage from '@/pages/ImportPage'
import InterviewPage from '@/pages/InterviewPage'
import InterviewPrepPage from '@/pages/InterviewPrepPage'
import InterviewsPage from '@/pages/InterviewsPage'
import SkillsPage from '@/pages/SkillsPage'
import NotificationsPage from '@/pages/NotificationsPage'
import ApplicationDetailPage from '@/pages/ApplicationDetailPage'
import ApplicationsPage from '@/pages/ApplicationsPage'
import AwaitingApprovalPage from '@/pages/AwaitingApprovalPage'
import ChangePasswordPage from '@/pages/ChangePasswordPage'
import ContactsPage from '@/pages/ContactsPage'
import CoverLetterPage from '@/pages/CoverLetterPage'
import HomePage from '@/pages/HomePage'
import JobDetailPage from '@/pages/JobDetailPage'
import JobSearchPage from '@/pages/JobSearchPage'
import JobsPage from '@/pages/JobsPage'
import LoginPage from '@/pages/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'
import OutboxPage from '@/pages/OutboxPage'
import ProfilePage from '@/pages/ProfilePage'
import RegisterPage from '@/pages/RegisterPage'
import ResumesPage from '@/pages/ResumesPage'
import ResumeVersionPage from '@/pages/ResumeVersionPage'
import RouteErrorPage from '@/pages/RouteErrorPage'
import SavedSearchesPage from '@/pages/SavedSearchesPage'
import ScanPage from '@/pages/ScanPage'
import SearchRunPage from '@/pages/SearchRunPage'
import SettingsPage from '@/pages/SettingsPage'
import SystemStatusPage from '@/pages/SystemStatusPage'
import TailoredResumePage from '@/pages/TailoredResumePage'
import TasksPage from '@/pages/TasksPage'

import { GuestOnly, RequireAdmin, RequireApproved, RequireAuth } from './guards'

const admin = (page) => <RequireAdmin>{page}</RequireAdmin>

/** Route table — grows per phase (see Phase 1 §8 page map). */
export const routes = [
  {
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: (
          <GuestOnly>
            <AuthLayout />
          </GuestOnly>
        ),
        children: [
          { path: 'login', element: <LoginPage /> },
          { path: 'register', element: <RegisterPage /> },
        ],
      },
      {
        element: (
          <RequireAuth>
            <AuthLayout />
          </RequireAuth>
        ),
        children: [{ path: 'awaiting-approval', element: <AwaitingApprovalPage /> }],
      },
      {
        element: (
          <RequireAuth>
            <RequireApproved>
              <AppLayout />
            </RequireApproved>
          </RequireAuth>
        ),
        children: [
          { index: true, element: <HomePage /> },
          { path: 'jobs', element: <JobsPage /> },
          { path: 'jobs/search', element: <JobSearchPage /> },
          { path: 'jobs/saved', element: <SavedSearchesPage /> },
          { path: 'jobs/scan', element: <ScanPage /> },
          { path: 'jobs/searches/:runId', element: <SearchRunPage /> },
          { path: 'jobs/:jobId', element: <JobDetailPage /> },
          { path: 'jobs/:jobId/tailored', element: <TailoredResumePage /> },
          { path: 'jobs/:jobId/cover-letter', element: <CoverLetterPage /> },
          { path: 'applications', element: <ApplicationsPage /> },
          { path: 'applications/:applicationId', element: <ApplicationDetailPage /> },
          { path: 'contacts', element: <ContactsPage /> },
          { path: 'outbox', element: <OutboxPage /> },
          { path: 'resumes', element: <ResumesPage /> },
          { path: 'resumes/:versionId', element: <ResumeVersionPage /> },
          { path: 'tasks', element: <TasksPage /> },
          { path: 'profile', element: <ProfilePage /> },
          { path: 'settings', element: <SettingsPage /> },
          { path: 'account/password', element: <ChangePasswordPage /> },
          { path: 'notifications', element: <NotificationsPage /> },
          { path: 'jobs/import', element: <ImportPage /> },
          { path: 'interviews', element: <InterviewsPage /> },
          { path: 'skills', element: <SkillsPage /> },
          { path: 'jobs/:jobId/prep', element: <InterviewPrepPage /> },
          { path: 'interviews/:interviewId', element: <InterviewPage /> },
          { path: 'admin/users', element: admin(<AdminUsersPage />) },
          { path: 'admin/audit', element: admin(<AuditLogPage />) },
          { path: 'admin/analytics', element: admin(<AnalyticsPage />) },
          { path: 'admin/system', element: admin(<SystemStatusPage />) },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]
