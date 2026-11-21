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
}

declare module 'claude-code' {
  interface PluginState {
    'task-progress-bar': { progress: Progress }
  }
}
