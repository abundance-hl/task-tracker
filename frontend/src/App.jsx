import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Archive, Check, CheckCircle2, Circle, ClipboardList, LoaderCircle, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, FieldGroup, FieldLabel, FieldError } from '@/components/ui/field'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { getSnapshot, request } from '@/lib/api'
import { cn } from '@/lib/utils'

export default function App() {
  const [snapshot, setSnapshot] = useState({ tasks: [], deletedTasks: [], stats: null })
  const [title, setTitle] = useState('')
  const [fieldError, setFieldError] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState('load')
  const [synced, setSynced] = useState(false)
  const busy = useRef(false)
  const input = useRef(null)
  const focusAfterMutation = useRef(false)
  const { tasks, deletedTasks, stats } = snapshot
  const disabled = Boolean(pending) || !synced

  async function refresh(initial = false) {
    if (busy.current) return
    busy.current = true
    setPending('load')
    setError('')
    setNotice('')
    try {
      setSnapshot(await getSnapshot())
      setSynced(true)
      if (!initial) setNotice('Tasks and statistics are up to date.')
    } catch (error) {
      setSynced(false)
      setError(`${error.message} Select Refresh to try again.`)
    } finally {
      busy.current = false
      setPending('')
    }
  }

  useEffect(() => { refresh(true) }, [])
  useEffect(() => {
    if (!pending && focusAfterMutation.current) {
      if (synced) input.current?.focus()
      focusAfterMutation.current = false
    }
  }, [pending, synced])
  useEffect(() => {
    if (!notice) return
    const timeout = setTimeout(() => setNotice(''), 7000)
    return () => clearTimeout(timeout)
  }, [notice])

  async function mutate(key, path, options, success) {
    if (busy.current || !synced) return
    busy.current = true
    setPending(key)
    setError('')
    setNotice('')
    let saved = false
    try {
      await request(path, options)
      saved = true
      if (key === 'add') setTitle('')
      setSnapshot(await getSnapshot())
      setSynced(true)
      setNotice(success)
    } catch (error) {
      const canCorrect = !saved && error.status === 400 && key === 'add'
      setSynced(canCorrect)
      if (canCorrect) {
        setFieldError(error.message)
      } else {
        setError(saved
          ? `Your change was saved, but the updated list could not be loaded. ${error.message} Refresh before making another change.`
          : error.status === 404
          ? 'This task is no longer available. Refresh to load the latest list before trying again.'
          : `${error.message} The action could not be confirmed. Refresh the list before trying again.`)
      }
    } finally {
      busy.current = false
      focusAfterMutation.current = true
      setPending('')
    }
  }

  function addTask(event) {
    event.preventDefault()
    const trimmed = title.trim()
    if (!trimmed) {
      setFieldError('Enter a task title before adding it.')
      input.current?.focus()
      return
    }
    const length = Array.from(trimmed).length
    if (length > 200) {
      setFieldError(`This title has ${length} characters. Shorten it to 200 or fewer.`)
      input.current?.focus()
      return
    }
    setFieldError('')
    mutate('add', '/tasks', { method: 'POST', body: JSON.stringify({ title: trimmed }) }, 'Task added. Your list and statistics are updated.')
  }

  return (
    <main className="workspace">
      <header className="page-header">
        <div>
          <h1>Tasks</h1>
          <p className="intro">A little structure for what needs to get done.</p>
        </div>
        <Badge variant="outline">Assessment prototype</Badge>
      </header>

      <section className="overview" aria-label="Task statistics" aria-busy={Boolean(pending)}>
        <dl className="statistics">
          <div><dt>Current tasks</dt><dd>{stats?.total ?? '—'}</dd><p className="stat-context">Excludes deleted tasks</p></div>
          <div><dt><Circle aria-hidden="true" />Pending</dt><dd>{stats?.pending ?? '—'}</dd><p className="stat-context">Current unfinished tasks</p></div>
          <div><dt><CheckCircle2 aria-hidden="true" />Completed overall</dt><dd>{stats?.completed_all_time ?? '—'}</dd><p className="stat-context">{stats ? `${stats.completed} current · ${stats.completed_deleted} deleted` : 'Includes deleted completions'}</p></div>
        </dl>
        {!synced && stats && <p className="stale-note">These counts may be out of date. Refresh to reconnect.</p>}
      </section>

      <section className="task-panel" aria-labelledby="task-list-heading">
        <form onSubmit={addTask} noValidate className="task-form">
          <FieldGroup>
            <Field data-invalid={Boolean(fieldError)}>
              <FieldLabel htmlFor="task-title">New task</FieldLabel>
              <div className="add-controls">
                <Input ref={input} id="task-title" placeholder="What needs to get done?" value={title}
                  onChange={event => { setTitle(event.target.value); setFieldError('') }}
                  aria-invalid={Boolean(fieldError)} aria-describedby={fieldError ? 'title-error' : undefined}
                  disabled={disabled} autoComplete="off" />
                <Button type="submit" disabled={disabled}>
                  {pending === 'add' ? <LoaderCircle className="spin" data-icon="inline-start" /> : <Plus data-icon="inline-start" />}
                  {pending === 'add' ? 'Adding…' : 'Add task'}
                </Button>
              </div>
              {fieldError && <FieldError id="title-error">{fieldError}</FieldError>}
            </Field>
          </FieldGroup>
        </form>

        <div className="task-list-header">
          <h2 id="task-list-heading">Your tasks</h2>
          <Button variant="ghost" type="button" onClick={() => refresh()} disabled={Boolean(pending)}>
            <RefreshCw className={cn(pending === 'load' && 'spin')} data-icon="inline-start" />
            {pending === 'load' ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>

        {error && <div className="feedback"><Alert variant="destructive"><AlertCircle /><AlertTitle>Tasks need a refresh</AlertTitle><AlertDescription>{error}</AlertDescription></Alert></div>}
        <div className="status-message" role="status" aria-live="polite" aria-atomic="true">
          {notice && <><CheckCircle2 aria-hidden="true" /><span>{notice}</span></>}
        </div>

        {!stats && pending ? <div className="loading-tasks" role="status"><span>Loading your tasks…</span><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div>
          : !stats ? <Empty><EmptyHeader><EmptyMedia variant="icon"><AlertCircle /></EmptyMedia><EmptyTitle>Tasks are unavailable</EmptyTitle><EmptyDescription>Refresh to load your tasks when the server is available.</EmptyDescription></EmptyHeader></Empty>
          : tasks.length === 0 ? <Empty><EmptyHeader><EmptyMedia variant="icon"><ClipboardList /></EmptyMedia><EmptyTitle>{deletedTasks.length ? 'No current tasks' : 'A clear place to start'}</EmptyTitle><EmptyDescription>{deletedTasks.length ? 'Add a new task above. Your previous tasks are in Deleted tasks below.' : 'Add your first task above. Your progress will appear here.'}</EmptyDescription></EmptyHeader></Empty>
          : <ul className="task-list" aria-label="Tasks" aria-busy={Boolean(pending)}>
            {tasks.map(task => <li key={task.id} className={cn('task-row', task.completed && 'is-complete')}>
              <span className="task-state-icon" aria-hidden="true">{task.completed ? <CheckCircle2 /> : <Circle />}</span>
              <div className="task-content">
                <p className="task-title">{task.title}</p>
                <Badge variant={task.completed ? 'success' : 'secondary'}>{task.completed ? 'Completed' : 'Pending'}</Badge>
              </div>
              <div className="task-actions">
                {!task.completed && <Button type="button" variant="outline" disabled={disabled} aria-label={`Complete ${task.title}`}
                  onClick={() => mutate(`complete-${task.id}`, `/tasks/${task.id}/complete`, { method: 'PUT' }, 'Task completed. Nice work.') }>
                  {pending === `complete-${task.id}` ? <LoaderCircle className="spin" data-icon="inline-start" /> : <Check data-icon="inline-start" />}Complete
                </Button>}
                <Button type="button" variant="ghost" disabled={disabled} aria-label={`Delete ${task.title}`}
                  onClick={() => mutate(`delete-${task.id}`, `/tasks/${task.id}`, { method: 'DELETE' }, 'Task moved to Deleted tasks.') }>
                  {pending === `delete-${task.id}` ? <LoaderCircle className="spin" data-icon="inline-start" /> : <Trash2 data-icon="inline-start" />}Delete
                </Button>
              </div>
            </li>)}
          </ul>}
      </section>
      <section className="archive-panel" aria-labelledby="archive-heading" aria-busy={Boolean(pending)}>
        <div className="archive-header">
          <div className="archive-heading"><Archive aria-hidden="true" /><h2 id="archive-heading">Deleted tasks</h2><Badge variant="secondary">{stats?.deleted ?? '—'}</Badge></div>
          <p>Kept for reference. Completed tasks still count toward Completed overall.</p>
        </div>
        {!stats ? <p className="archive-empty">{pending ? 'Loading your history…' : 'Refresh to load your history.'}</p>
          : deletedTasks.length === 0 ? <p className="archive-empty">No deleted tasks yet. Tasks you delete will appear here.</p>
          : <ul className="task-list" aria-label="Deleted tasks">
            {deletedTasks.map(task => <li key={task.id} className="archive-row">
              <div className="task-content"><p className="task-title">{task.title}</p><div className="archive-metadata"><Badge variant={task.completed ? 'success' : 'secondary'}>{task.completed ? 'Completed' : 'Not completed'}</Badge><time dateTime={task.deleted_at}>Deleted {new Date(task.deleted_at).toLocaleString(undefined, {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}</time></div></div>
            </li>)}
          </ul>}
      </section>
      <footer>Carbon Arc take-home · Current and deleted tasks are saved across restarts.</footer>
    </main>
  )
}
