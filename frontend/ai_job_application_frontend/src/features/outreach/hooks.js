import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'
import { isActive } from '@/features/tasks/api'
import { useTaskPolling } from '@/features/tasks/hooks'

import { automationApi, contactsApi, emailsApi, gmailApi, repliesApi } from './api'

const POLL_MS = 3000

// ---------- Gmail ----------

export function useGmailStatus() {
  return useQuery({ queryKey: queryKeys.gmail.status(), queryFn: gmailApi.status })
}

export function useConnectGmail() {
  return useMutation({
    mutationFn: gmailApi.connect,
    // The Google consent page; Google sends the browser back to Settings.
    onSuccess: ({ auth_url: url }) => window.location.assign(url),
    onError: (error) => toast.error(error.message),
  })
}

export function useDisconnectGmail() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: gmailApi.disconnect,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.gmail.status() })
      toast.success('Gmail disconnected.')
    },
    onError: (error) => toast.error(error.message),
  })
}

// ---------- contacts ----------

export function useContacts(filters) {
  return useQuery({
    queryKey: queryKeys.contacts.list(filters),
    queryFn: () => contactsApi.list(filters),
    placeholderData: keepPreviousData,
  })
}

export function useExportContacts() {
  return useMutation({
    mutationFn: contactsApi.exportCsv,
    onSuccess: (name) => toast.success(`Downloaded ${name}`),
    onError: (error) => toast.error(error.message),
  })
}

export function useContactCounts() {
  return useQuery({ queryKey: queryKeys.contacts.counts(), queryFn: contactsApi.counts })
}

function useContactMutation(mutationFn, success) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.all() })
      queryClient.invalidateQueries({ queryKey: queryKeys.applications.all() })
      queryClient.invalidateQueries({ queryKey: queryKeys.emails.all() })
      if (success) toast.success(typeof success === 'function' ? success(result) : success)
    },
    onError: (error) => toast.error(error.message),
  })
}

export const useCreateContact = () => useContactMutation(contactsApi.create, 'Contact added.')
export const useUpdateContact = () =>
  useContactMutation(({ id, changes }) => contactsApi.update(id, changes))
export const useVerifyContact = () =>
  useContactMutation(contactsApi.verify, (c) => `Checked: ${c.email}`)
export const useDeleteContact = () => useContactMutation(contactsApi.remove, 'Contact deleted.')

export function useBlocked() {
  return useQuery({ queryKey: queryKeys.contacts.blocked(), queryFn: contactsApi.blocked })
}
export const useBlock = () => useContactMutation(contactsApi.block, 'Added to do-not-contact.')
export const useUnblock = () => useContactMutation(contactsApi.unblock, 'Removed.')

/** Follow a background task; refresh `keys` when it is done. */
function useFollow(taskId, keys, onSuccess) {
  const queryClient = useQueryClient()
  const task = useTaskPolling(taskId).data
  const status = task?.status
  useEffect(() => {
    if (!task || isActive(task)) return
    keys.forEach((key) => queryClient.invalidateQueries({ queryKey: key }))
    if (status === 'succeeded') onSuccess?.(task)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- react once per finished task
  }, [task?.id, status])
  return task
}

/** "Find on LinkedIn": Apify run + AI reading of each post (takes a minute or two). */
export function useDiscoverContacts() {
  const mutation = useMutation({
    mutationFn: contactsApi.discover,
    onError: (error) => toast.error(error.message),
  })
  const task = useFollow(
    mutation.data?.task_id ?? null,
    [queryKeys.contacts.all(), queryKeys.jobs.all(), queryKeys.usage()],
    (finished) => {
      const r = finished.result ?? {}
      toast.success(
        `${r.new_contacts} new contact${r.new_contacts === 1 ? '' : 's'} from ${r.posts} posts.`,
      )
    },
  )
  return {
    start: (body) => mutation.mutate(body),
    task,
    running: mutation.isPending || isActive(task),
  }
}

// ---------- emails ----------

export function useApplicationEmail(applicationId) {
  return useQuery({
    queryKey: queryKeys.emails.forApplication(applicationId),
    queryFn: () => emailsApi.forApplication(applicationId),
    enabled: Boolean(applicationId),
    // Scheduled/sending emails change on their own (the worker sends them).
    refetchInterval: (query) =>
      ['queued', 'sending'].includes(query.state.data?.status) ? POLL_MS : false,
  })
}

export function useDraftEmail(applicationId) {
  const mutation = useMutation({
    mutationFn: (contactId) => emailsApi.draft(applicationId, contactId),
    onError: (error) => toast.error(error.message),
  })
  const task = useFollow(
    mutation.data?.task_id ?? null,
    [queryKeys.emails.all(), queryKeys.applications.all()],
    () => toast.success('Email drafted — review it before approving.'),
  )
  return {
    start: (contactId) => mutation.mutate(contactId),
    task,
    running: mutation.isPending || isActive(task),
  }
}

export function useOutbox(filters) {
  return useQuery({
    queryKey: queryKeys.emails.outbox(filters),
    queryFn: () => emailsApi.outbox(filters),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.items.some((e) => ['queued', 'sending'].includes(e.status))
        ? POLL_MS
        : false,
  })
}

export function useOutboxSummary() {
  return useQuery({ queryKey: queryKeys.emails.summary(), queryFn: emailsApi.summary })
}

function useEmailMutation(mutationFn, success) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (result, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.emails.all() })
      queryClient.invalidateQueries({ queryKey: queryKeys.applications.all() })
      const message = typeof success === 'function' ? success(result, variables) : success
      if (message) toast.success(message)
    },
    onError: (error) => toast.error(error.message),
  })
}

export const useEditEmail = () =>
  useEmailMutation(({ id, changes }) => emailsApi.edit(id, changes), 'Draft saved.')

const ACTION_TOASTS = {
  approve: 'Approved — it is sent at the scheduled time.',
  reject: 'Rejected — this email will not be sent.',
  cancel: 'Sending cancelled — the email is a draft again.',
  retry: 'Back to draft — review and approve it again.',
}

/** approve | reject | cancel | retry; `approveContact` approves a pending contact too. */
export const useEmailAction = () =>
  useEmailMutation(
    ({ id, action, approveContact }) => emailsApi.action(id, action, { approveContact }),
    (_, { action }) => ACTION_TOASTS[action],
  )

// ---------- automation & replies (Phase 13) ----------

const RUN_ACTIVE = ['queued', 'running']

export function useAutomation() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: queryKeys.automation.status(),
    queryFn: automationApi.status,
    refetchInterval: (q) => (RUN_ACTIVE.includes(q.state.data?.last_run?.status) ? POLL_MS : false),
  })
  const run = query.data?.last_run
  // When a run finishes, the drafts it made must appear in the Outbox tabs at once
  // (found live: the panel said "1 ready" while the tab still showed 0).
  const finishedRun = run && !RUN_ACTIVE.includes(run.status) ? run.task_id : null
  const seen = useRef(undefined)
  useEffect(() => {
    if (seen.current === undefined) {
      seen.current = finishedRun // first load: nothing new
      return
    }
    if (finishedRun && finishedRun !== seen.current) {
      ;[queryKeys.emails.all(), queryKeys.applications.all(), queryKeys.jobs.all()].forEach((key) =>
        queryClient.invalidateQueries({ queryKey: key }),
      )
    }
    seen.current = finishedRun
  }, [finishedRun, queryClient])
  return query
}

export function useRunAutomation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: automationApi.run,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.automation.status() })
      toast.info('Automation started — it takes a few minutes.')
    },
    onError: (error) => toast.error(error.message),
  })
}

export function usePlatformSettings({ enabled }) {
  return useQuery({
    queryKey: queryKeys.automation.platform(),
    queryFn: automationApi.platform,
    enabled,
  })
}

export function useUpdatePlatform() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: automationApi.updatePlatform,
    onSuccess: (saved, changes) => {
      queryClient.setQueryData(queryKeys.automation.platform(), saved)
      queryClient.invalidateQueries({ queryKey: queryKeys.automation.status() })
      queryClient.invalidateQueries({ queryKey: queryKeys.usage() })
      if (!('automation_fetch_enabled' in changes)) toast.success('Usage limits saved.')
      else
        toast.success(
          saved.automation_fetch_enabled
            ? '"Fetch new jobs & automate" is now available.'
            : '"Fetch new jobs & automate" is locked.',
        )
    },
    onError: (error) => toast.error(error.message),
  })
}

export function useReplies(applicationId) {
  return useQuery({
    queryKey: queryKeys.emails.replies(applicationId),
    queryFn: () => repliesApi.forApplication(applicationId),
    enabled: Boolean(applicationId),
  })
}

export function useConfirmReply() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, accept }) => repliesApi.confirm(id, accept),
    onSuccess: (_, { accept }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.emails.all() })
      queryClient.invalidateQueries({ queryKey: queryKeys.applications.all() })
      toast.success(accept ? 'Status updated.' : 'Dismissed.')
    },
    onError: (error) => toast.error(error.message),
  })
}

export const useApproveBatch = () =>
  useEmailMutation(
    ({ ids, approveContacts }) => emailsApi.approveBatch(ids, approveContacts),
    (result) => {
      const failed = Object.keys(result.errors).length
      return `${result.approved.length} approved${failed ? `, ${failed} could not be approved` : ''}.`
    },
  )
