import { describe, expect, it, vi } from 'vitest'

import {
  applyAgentEvent,
  hydrateAgentEventState,
  readSseEvents,
  streamAgentEvents
} from './agentStream'


const responseWithByteCuts = (text, cuts) => {
  const bytes = new TextEncoder().encode(text)
  const chunks = []
  let start = 0
  for (const end of cuts) {
    chunks.push(bytes.slice(start, end))
    start = end
  }
  chunks.push(bytes.slice(start))
  return new Response(
    new ReadableStream({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(chunk))
        controller.close()
      }
    }),
    { headers: { 'Content-Type': 'text/event-stream' } }
  )
}


describe('readSseEvents', () => {
  it('parses versioned events across arbitrary UTF-8 network chunks', async () => {
    const body = [
      'id: 1\r\ndata: {"version":1,"type":"thinking","message_id":7,"sequence":1,"timestamp":"2026-08-18T00:00:00.000Z","payload":{"kind":"stage","text":"分析資料"}}\r\n\r\n',
      'id: 2\ndata: {"version":1,"type":"answer_delta","message_id":7,"sequence":2,"timestamp":"2026-08-18T00:00:01.000Z","payload":{"delta":"完成"}}\n\n'
    ].join('')
    const response = responseWithByteCuts(body, [1, 9, 57, 131, 166, 205])

    const events = []
    for await (const event of readSseEvents(response)) {
      events.push(event)
    }

    expect(events.map((event) => event.type)).toEqual(['thinking', 'answer_delta'])
    expect(events.map((event) => event.sequence)).toEqual([1, 2])
    expect(events[0].payload.text).toBe('分析資料')
    expect(events[1].payload.delta).toBe('完成')
  })
})


describe('applyAgentEvent', () => {
  it('deduplicates ordered events and preserves execution details with partial text', () => {
    const base = {
      id: '7',
      content: '',
      status: 'pending',
      lastSequence: 0,
      executionEvents: []
    }
    const envelope = (sequence, type, payload) => ({
      version: 1,
      type,
      message_id: 7,
      sequence,
      timestamp: `2026-08-18T00:00:0${sequence}.000Z`,
      payload
    })

    let message = applyAgentEvent(
      base,
      envelope(1, 'thinking', { kind: 'stage', text: '分析資料' })
    )
    message = applyAgentEvent(
      message,
      envelope(2, 'tool_call', { call_id: 'call-1', name: 'lookup', status: 'started' })
    )
    message = applyAgentEvent(
      message,
      envelope(3, 'tool_result', { call_id: 'call-1', name: 'lookup', status: 'success' })
    )
    message = applyAgentEvent(message, envelope(4, 'answer_delta', { delta: '完成' }))
    message = applyAgentEvent(message, envelope(4, 'answer_delta', { delta: '完成' }))
    message = applyAgentEvent(message, envelope(5, 'stopped', { reason: 'user_requested' }))
    message = applyAgentEvent(message, envelope(6, 'answer_delta', { delta: '不應出現' }))

    expect(message.content).toBe('完成')
    expect(message.status).toBe('stopped')
    expect(message.lastSequence).toBe(5)
    expect(message.thinkingStatus).toBe('')
    expect(message.executionEvents.map((event) => event.type)).toEqual([
      'thinking',
      'tool_call',
      'tool_result'
    ])
  })
})


describe('hydrateAgentEventState', () => {
  it('restores persisted execution details without appending answer text twice', () => {
    const events = [
      { version: 1, type: 'thinking', message_id: 7, sequence: 1, timestamp: 'one', payload: { text: 'Checking' } },
      { version: 1, type: 'answer_delta', message_id: 7, sequence: 2, timestamp: 'two', payload: { delta: 'partial' } }
    ]

    const hydrated = hydrateAgentEventState({
      id: '7',
      content: 'partial',
      status: 'pending'
    }, events)

    expect(hydrated.content).toBe('partial')
    expect(hydrated.lastSequence).toBe(2)
    expect(hydrated.thinkingStatus).toBe('Checking')
    expect(hydrated.executionEvents).toEqual([events[0]])
  })
})


describe('streamAgentEvents', () => {
  it('authenticates with a bearer header and resumes by sequence without a URL token', async () => {
    const body = 'id: 4\ndata: {"version":1,"type":"done","message_id":7,"sequence":4,"timestamp":"2026-08-18T00:00:04.000Z","payload":{}}\n\n'
    const fetchImpl = vi.fn(async () => responseWithByteCuts(body, [11, 49]))
    const controller = new AbortController()

    const events = []
    for await (const event of streamAgentEvents({
      url: '/api/messages/7/stream',
      token: 'browser-secret',
      afterSequence: 3,
      signal: controller.signal,
      fetchImpl
    })) {
      events.push(event)
    }

    expect(events).toHaveLength(1)
    expect(fetchImpl).toHaveBeenCalledWith(
      '/api/messages/7/stream?after_sequence=3',
      expect.objectContaining({
        headers: { Authorization: 'Bearer browser-secret', Accept: 'text/event-stream' },
        signal: controller.signal
      })
    )
    expect(fetchImpl.mock.calls[0][0]).not.toContain('browser-secret')
  })
})
