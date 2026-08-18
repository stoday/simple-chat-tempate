// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ChatMessage from './ChatMessage.vue'


describe('ChatMessage agent execution details', () => {
  it('shows thinking, correlates tool activity, and keeps details collapsed', async () => {
    const message = {
      id: '11',
      role: 'assistant',
      content: '部分回答',
      status: 'pending',
      thinkingStatus: '正在查詢資料',
      files: [],
      executionEvents: [
        {
          type: 'tool_call',
          sequence: 2,
          payload: { call_id: 'call-1', name: 'lookup_customer', status: 'started', arguments: { id: 7 } }
        },
        {
          type: 'tool_result',
          sequence: 3,
          payload: { call_id: 'call-1', name: 'lookup_customer', status: 'success', result: { count: 2 } }
        }
      ]
    }
    const wrapper = mount(ChatMessage, { props: { message } })

    expect(wrapper.text()).toContain('部分回答')
    expect(wrapper.text()).toContain('正在查詢資料')
    const details = wrapper.get('[data-testid="execution-details"]')
    expect(details.attributes('open')).toBeUndefined()
    expect(details.text()).toContain('執行詳情')
    expect(details.text()).toContain('lookup_customer')
    expect(details.text()).toContain('call-1')
    expect(details.text()).toContain('count')

    await wrapper.setProps({ message: { ...message, status: 'stopped', thinkingStatus: '' } })
    expect(wrapper.text()).toContain('已停止生成')
  })

  it('shows the safe stream error while preserving partial content', () => {
    const wrapper = mount(ChatMessage, { props: { message: {
      id: '12',
      role: 'assistant',
      content: '可保留的部分',
      status: 'error',
      streamError: { message: 'Response generation failed.' },
      files: [],
      executionEvents: []
    } } })

    expect(wrapper.text()).toContain('可保留的部分')
    expect(wrapper.text()).toContain('Response generation failed.')
  })
})
