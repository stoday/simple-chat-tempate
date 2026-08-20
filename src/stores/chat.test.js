// @vitest-environment jsdom

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiClient } = vi.hoisted(() => ({
  apiClient: {
    defaults: { baseURL: '/api' },
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  }
}))

vi.mock('../services/api', () => ({ default: apiClient }))

import { useChatStore } from './chat'


const event = (messageId, sequence, type, payload = {}) => ({
  version: 1,
  type,
  message_id: messageId,
  sequence,
  timestamp: `2026-08-18T00:00:0${sequence}.000Z`,
  payload
})


const streamResponse = (events) => {
  const bytes = new TextEncoder().encode(events
    .map((item) => `id: ${item.sequence}\ndata: ${JSON.stringify(item)}\n\n`)
    .join(''))
  return new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(bytes.slice(0, 17))
      controller.enqueue(bytes.slice(17))
      controller.close()
    }
  }), { headers: { 'Content-Type': 'text/event-stream' } })
}


describe('chat store agent stream', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('auth_token', 'browser-token')
  })

  it('applies fetch-streamed execution events to the pending assistant message', async () => {
    apiClient.post.mockImplementation(async (url) => {
      if (url === '/conversations') {
        return { data: { id: 1, title: 'Streaming', created_at: 'now', updated_at: 'now' } }
      }
      if (url === '/messages') {
        return { data: {
          message: { id: 10, conversation_id: 1, sender_type: 'user', content: 'Hello', status: 'completed', created_at: 'now' },
          reply: { id: 11, conversation_id: 1, sender_type: 'assistant', content: '', status: 'pending', created_at: 'now' }
        } }
      }
      throw new Error(`Unexpected POST ${url}`)
    })
    globalThis.fetch = vi.fn(async () => streamResponse([
      event(11, 1, 'conversation_title', { conversation_title: 'Generated title' }),
      event(11, 2, 'thinking', { kind: 'stage', text: 'Checking data' }),
      event(11, 3, 'answer_delta', { delta: 'Streaming reply' }),
      event(11, 4, 'done', { conversation_title: 'Generated title' })
    ]))

    const store = useChatStore()
    await store.createNewChat('Streaming')
    await store.sendMessage('Hello')

    await vi.waitFor(() => {
      expect(store.currentMessages.find((item) => item.id === '11')?.status).toBe('completed')
    })
    const assistant = store.currentMessages.find((item) => item.id === '11')
    expect(assistant.content).toBe('Streaming reply')
    expect(assistant.executionEvents.map((item) => item.type)).toEqual(['thinking'])
    expect(store.conversations.find((item) => item.id === '1')?.title).toBe('Generated title')
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/messages/11/stream?after_sequence=0',
      expect.objectContaining({
        headers: { Authorization: 'Bearer browser-token', Accept: 'text/event-stream' }
      })
    )
  })

  it('aborts the fetch stream after stop succeeds and keeps partial text', async () => {
    apiClient.post.mockImplementation(async (url) => {
      if (url === '/conversations') {
        return { data: { id: 1, title: 'Stop', created_at: 'now', updated_at: 'now' } }
      }
      if (url === '/messages') {
        return { data: {
          message: { id: 20, conversation_id: 1, sender_type: 'user', content: 'Stop', status: 'completed', created_at: 'now' },
          reply: { id: 21, conversation_id: 1, sender_type: 'assistant', content: '', status: 'pending', created_at: 'now' }
        } }
      }
      if (url === '/messages/21/stop') {
        return { data: { id: 21, conversation_id: 1, sender_type: 'assistant', content: 'Partial', status: 'stopped', stopped_at: 'later', created_at: 'now' } }
      }
      throw new Error(`Unexpected POST ${url}`)
    })
    globalThis.fetch = vi.fn(async (_url, options) => {
      const bytes = new TextEncoder().encode(`id: 1\ndata: ${JSON.stringify(event(21, 1, 'answer_delta', { delta: 'Partial' }))}\n\n`)
      return new Response(new ReadableStream({
        start(controller) {
          controller.enqueue(bytes)
          options.signal.addEventListener('abort', () => {
            controller.error(new DOMException('Aborted', 'AbortError'))
          })
        }
      }), { headers: { 'Content-Type': 'text/event-stream' } })
    })

    const store = useChatStore()
    await store.createNewChat('Stop')
    await store.sendMessage('Stop')
    await vi.waitFor(() => {
      expect(store.currentMessages.find((item) => item.id === '21')?.content).toBe('Partial')
    })
    await store.stopGenerating()

    const assistant = store.currentMessages.find((item) => item.id === '21')
    expect(assistant.content).toBe('Partial')
    expect(assistant.status).toBe('stopped')
    expect(globalThis.fetch.mock.calls[0][1].signal.aborted).toBe(true)
  })

  it('resumes after persisted events when a pending conversation reloads', async () => {
    apiClient.post.mockResolvedValue({
      data: { id: 1, title: 'Replay', created_at: 'now', updated_at: 'now' }
    })
    apiClient.get.mockResolvedValue({ data: {
      conversation_title: 'Replay',
      messages: [{
        id: 31,
        conversation_id: 1,
        sender_type: 'assistant',
        content: 'Partial',
        status: 'pending',
        created_at: 'now',
        events: [
          event(31, 1, 'thinking', { text: 'Checking' }),
          event(31, 2, 'answer_delta', { delta: 'Partial' })
        ]
      }]
    } })
    globalThis.fetch = vi.fn(async () => streamResponse([event(31, 3, 'done')]))

    const store = useChatStore()
    await store.createNewChat('Replay')
    await store.selectConversation('1')

    await vi.waitFor(() => expect(store.currentMessages[0]?.status).toBe('completed'))
    expect(store.currentMessages[0].content).toBe('Partial')
    expect(store.currentMessages[0].executionEvents[0].type).toBe('thinking')
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/messages/31/stream?after_sequence=2',
      expect.any(Object)
    )
  })

  it('reconnects from the last sequence when a stream closes before a terminal event', async () => {
    apiClient.post.mockImplementation(async (url) => {
      if (url === '/conversations') {
        return { data: { id: 1, title: 'Reconnect', created_at: 'now', updated_at: 'now' } }
      }
      if (url === '/messages') {
        return { data: {
          message: { id: 40, conversation_id: 1, sender_type: 'user', content: 'Hello', status: 'completed', created_at: 'now' },
          reply: { id: 41, conversation_id: 1, sender_type: 'assistant', content: '', status: 'pending', created_at: 'now' }
        } }
      }
      throw new Error(`Unexpected POST ${url}`)
    })
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(streamResponse([event(41, 1, 'answer_delta', { delta: 'Part' })]))
      .mockResolvedValueOnce(streamResponse([
        event(41, 2, 'answer_delta', { delta: ' two' }),
        event(41, 3, 'done')
      ]))

    const store = useChatStore()
    await store.createNewChat('Reconnect')
    await store.sendMessage('Hello')

    await vi.waitFor(() => {
      expect(store.currentMessages.find((item) => item.id === '41')?.status).toBe('completed')
    })
    expect(store.currentMessages.find((item) => item.id === '41')?.content).toBe('Part two')
    expect(globalThis.fetch.mock.calls[1][0]).toBe('/api/messages/41/stream?after_sequence=1')
  })
})
