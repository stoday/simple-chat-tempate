const FRAME_BOUNDARY = /\r?\n\r?\n/
const TERMINAL_TYPES = new Set(['done', 'error', 'stopped'])


export class AgentStreamGapError extends Error {
  constructor(expected, received) {
    super(`Agent stream sequence gap: expected ${expected}, received ${received}`)
    this.name = 'AgentStreamGapError'
    this.expected = expected
    this.received = received
  }
}


export const applyAgentEvent = (message, event) => {
  if (String(event.message_id) !== String(message.id)) return message
  const lastSequence = message.lastSequence || 0
  if (message.streamTerminal || event.sequence <= lastSequence) return message
  if (event.sequence !== lastSequence + 1) {
    throw new AgentStreamGapError(lastSequence + 1, event.sequence)
  }

  const next = {
    ...message,
    lastSequence: event.sequence,
    executionEvents: [...(message.executionEvents || [])]
  }
  if (event.type === 'answer_delta') {
    next.content = `${message.content || ''}${event.payload?.delta || ''}`
  } else if (event.type === 'thinking') {
    next.thinkingStatus = event.payload?.text || ''
    next.executionEvents.push(event)
  } else if (event.type === 'tool_call' || event.type === 'tool_result') {
    next.executionEvents.push(event)
  } else if (event.type === 'workflow_stage') {
    next.executionEvents.push(event)
  } else if (event.type === 'done') {
    next.status = 'completed'
    next.streamTerminal = true
  } else if (event.type === 'stopped') {
    next.status = 'stopped'
    next.stoppedAt = event.timestamp
    next.streamTerminal = true
  } else if (event.type === 'error') {
    next.status = 'error'
    next.streamError = event.payload
    next.streamTerminal = true
  }
  if (TERMINAL_TYPES.has(event.type)) next.thinkingStatus = ''
  return next
}


export const hydrateAgentEventState = (message, events = []) => {
  const ordered = [...events]
    .filter((event) => String(event.message_id) === String(message.id))
    .sort((left, right) => left.sequence - right.sequence)
  const executionEvents = ordered.filter((event) => (
    event.type === 'thinking' || event.type === 'tool_call' || event.type === 'tool_result' || event.type === 'workflow_stage'
  ))
  const terminal = [...ordered].reverse().find((event) => TERMINAL_TYPES.has(event.type))
  const latestThinking = [...ordered].reverse().find((event) => event.type === 'thinking')
  const error = terminal?.type === 'error' ? terminal.payload : null

  return {
    ...message,
    lastSequence: ordered.at(-1)?.sequence || 0,
    executionEvents,
    thinkingStatus: terminal ? '' : (latestThinking?.payload?.text || ''),
    streamTerminal: Boolean(terminal),
    streamError: error
  }
}


const parseFrame = (frame) => {
  const dataLines = []
  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator === -1 ? line : line.slice(0, separator)
    const rawValue = separator === -1 ? '' : line.slice(separator + 1)
    const value = rawValue.startsWith(' ') ? rawValue.slice(1) : rawValue
    if (field === 'data') dataLines.push(value)
  }
  if (!dataLines.length) return null
  const event = JSON.parse(dataLines.join('\n'))
  if (event.version !== 1) {
    throw new Error(`Unsupported agent stream version: ${event.version}`)
  }
  return event
}


export async function* readSseEvents(response) {
  if (!response.ok) {
    throw new Error(`Agent stream request failed with status ${response.status}`)
  }
  if (!response.body) {
    throw new Error('Agent stream response has no readable body')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })

    let boundary = FRAME_BOUNDARY.exec(buffer)
    while (boundary) {
      const frame = buffer.slice(0, boundary.index)
      buffer = buffer.slice(boundary.index + boundary[0].length)
      const event = parseFrame(frame)
      if (event) yield event
      boundary = FRAME_BOUNDARY.exec(buffer)
    }

    if (done) break
  }

  if (buffer.trim()) {
    const event = parseFrame(buffer)
    if (event) yield event
  }
}


export async function* streamAgentEvents({
  url,
  token,
  afterSequence = 0,
  signal,
  fetchImpl = fetch
}) {
  const separator = url.includes('?') ? '&' : '?'
  const requestUrl = `${url}${separator}after_sequence=${Math.max(0, afterSequence)}`
  const response = await fetchImpl(requestUrl, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'text/event-stream'
    },
    signal
  })
  yield* readSseEvents(response)
}
