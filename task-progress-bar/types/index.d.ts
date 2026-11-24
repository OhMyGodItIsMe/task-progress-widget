export type Progress = {
  total: number
  completed: number
  label: string
  done: boolean
  running: boolean
  // Epoch ms when the current in-progress step began; 0 before any task.
  stepStartedAt: number
  // Start of the message that began this turn, as the widget's row name.
  prompt: string
  // Why the session is waiting on the person, or '' when it isn't:
  // 'permission' (a tool needs approval), 'question' (Claude asked something
  // mid-turn), 'answer' (the turn ended on a question for the person).
  waiting: Waiting
}

export type Waiting = '' | 'permission' | 'question' | 'answer'

declare module 'claude-code' {
  interface PluginState {
    'task-progress-bar': { progress: Progress }
  }
}
