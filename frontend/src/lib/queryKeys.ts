export const queryKeys = {
  tasks: ['tasks'] as const,
  task: (taskId: string) => ['tasks', taskId] as const,
  taskContent: (taskId: string) => ['tasks', taskId, 'content'] as const,
  health: ['health'] as const,
} as const;
