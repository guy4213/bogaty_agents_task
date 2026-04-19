import type { TaskStatusResponse } from '@/types/api';

type NodeState = 'done' | 'active' | 'pending' | 'failed' | 'hidden';

interface Node { id: string; label: string; }

const ALL_NODES: Node[] = [
  { id: 'orchestrator', label: 'Orchestrator' },
  { id: 'content',      label: 'Content' },
  { id: 'image',        label: 'Image' },
  { id: 'video',        label: 'Video' },
  { id: 'validator',    label: 'Validator' },
];

function deriveNodeStates(task: TaskStatusResponse): Record<string, NodeState> {
  const { status, content_type, quantity_delivered, quantity_failed } = task;
  const pipeline =
    content_type === 'comment' ? 'text_only' :
    content_type === 'reels'   ? 'full_video' : 'text_image';

  const visible: Record<string, boolean> = {
    orchestrator: true,
    content:      true,
    image:        pipeline !== 'text_only',
    video:        pipeline === 'full_video',
    validator:    true,
  };

  const states: Record<string, NodeState> = Object.fromEntries(
    ALL_NODES.map((n) => [n.id, visible[n.id] ? 'pending' : 'hidden'])
  );

  if (status === 'pending') {
    states['orchestrator'] = 'active';
    return states;
  }
  if (status === 'failed' && quantity_delivered === 0) {
    states['orchestrator'] = 'done';
    states['content'] = 'failed';
    return states;
  }
  if (status === 'completed' || status === 'partial') {
    for (const n of ALL_NODES) {
      if (states[n.id] !== 'hidden') states[n.id] = 'done';
    }
    if (status === 'partial' && quantity_failed > 0) states['validator'] = 'done';
    return states;
  }
  // processing
  states['orchestrator'] = 'done';
  if (quantity_delivered > 0) {
    states['content'] = 'done';
    if (pipeline !== 'text_only') states['image'] = 'done';
    if (pipeline === 'full_video') {
      states['video'] = 'active';
    } else {
      states['validator'] = 'active';
    }
  } else {
    states['content'] = 'active';
  }
  return states;
}

const ICON: Record<NodeState, string> = {
  done: '✓', active: '⏳', pending: '○', failed: '✗', hidden: '',
};

function nodeStyle(state: NodeState): React.CSSProperties {
  if (state === 'done')    return { background: 'var(--success)',      color: '#fff' };
  if (state === 'active')  return { background: 'var(--accent)',       color: '#fff' };
  if (state === 'failed')  return { background: 'var(--danger)',       color: '#fff' };
  return { background: 'var(--surface3)', color: 'var(--fg3)', border: '1px solid var(--border2)' };
}

function labelStyle(state: NodeState): React.CSSProperties {
  if (state === 'active') return { color: 'var(--accent-light)', fontWeight: 500 };
  if (state === 'done')   return { color: 'var(--fg2)' };
  if (state === 'failed') return { color: 'var(--danger)' };
  return { color: 'var(--fg3)' };
}

interface PipelineStripProps { task: TaskStatusResponse; }

export function PipelineStrip({ task }: PipelineStripProps) {
  const states = deriveNodeStates(task);

  return (
    <div
      className="flex items-center gap-1 px-4 py-3 rounded-[var(--radius-sm)] overflow-x-auto"
      style={{ background: 'var(--surface2)', border: '1px solid var(--border)' }}
    >
      {ALL_NODES.map((node, i) => {
        const state = states[node.id];
        const isHidden = state === 'hidden';
        const isActive = state === 'active';
        const isLast = i === ALL_NODES.length - 1;

        return (
          <div
            key={node.id}
            className="flex items-center"
            style={{ opacity: isHidden ? 0.2 : 1 }}
          >
            <div className="flex flex-col items-center gap-1 min-w-[56px]">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all ${isActive ? 'animate-pulse' : ''}`}
                style={nodeStyle(state)}
              >
                {ICON[state]}
              </div>
              <span className="text-[11px]" style={labelStyle(state)}>
                {node.label}
              </span>
            </div>
            {!isLast && (
              <div
                className="h-px w-5 mx-1 mb-4"
                style={{ background: state === 'done' ? 'var(--fg3)' : 'var(--border2)' }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
