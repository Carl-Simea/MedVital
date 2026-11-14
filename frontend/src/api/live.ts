import type { LiveResponse } from '../domain/live'

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

export async function fetchLive(
  baseUrl = '/api/v1',
  fetchImpl: FetchLike = (input, init) => fetch(input, init),
  signal?: AbortSignal,
): Promise<LiveResponse> {
  const init: RequestInit = signal ? { signal } : {}
  const response = await fetchImpl(`${baseUrl}/live`, init)
  if (!response.ok) throw new Error(`gateway answered HTTP ${response.status}`)
  return (await response.json()) as LiveResponse
}
