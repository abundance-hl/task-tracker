export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.status = status
  }
}

export async function request(path, options = {}) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15000)
  try {
    const response = await fetch(`/api${path}`, {
      ...options,
      headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
      signal: controller.signal,
      cache: 'no-store',
    })
    if (response.status === 204) return null
    const body = await response.json().catch(() => null)
    if (!response.ok) {
      throw new ApiError(body?.error?.message || `The server could not complete this request (${response.status}).`, response.status)
    }
    if (body === null) throw new ApiError('The server returned an unreadable response.')
    return body
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(error.name === 'AbortError'
      ? 'The server took too long to respond.'
      : 'Could not reach the server. Check your connection.')
  } finally {
    clearTimeout(timeout)
  }
}

export async function getSnapshot() {
  return request('/tasks/snapshot')
}
