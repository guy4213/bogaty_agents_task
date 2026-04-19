import type { TaskStatusResponse } from '@/types/api';

type NodeState = 'done' | 'active' | 'pending' | 'failed' | 'hidden';

interface Node {
  id: string;
  label: string;
}

const ALL_NODES: Node[] = [
  { id: 'orchestrator', label: 'Orchestrator' },
  { id: 'content', label: 'Content' },
  { id: 'image', label: 'Image' },
  { id: 'video', label: 'Video' },
  { id: 'validator', label: 'Validator' },
];

function deriveNodeStates(
  task: TaskStatusResponse,
): Record<string, NodeState> {
  const { status, content_type, quantity_delivered, quantity_failed } = task;
  const pipeline =
    content_type === 'comment'
      ? 'text_only'
      : content_type === 'reels'
        ? 'full_video'
        : 'text_image';

  const visible: Record<string, boolean> = {
    orchestrator: true,
    content: true,
    image: pipeline !== 'text_only',
    video: pipeline === 'full_video',
    validator: true,
  };

  const states: Record<string, NodeState> = {};

  for (const node of ALL_NODES) {
    if (!visible[node.id]) {
      states[node.id] = 'hidden';
      continue;
    }
    states[node.id] = 'pending';
  }

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
    for (const node of ALL_NODES) {
      if (states[node.id] !== 'hidden') {
        states[node.id] = 'done';
      }
    }
    if (status === 'partial' && quantity_failed > 0) {
      states['validator'] = 'done';
    }
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

const NODE_ICON: Record<NodeState, string> = {
  done: '✓',
  active: '⏳',
  pending: '○',
  failed: '✗',
  hidden: '',
};

const NODE_STYLE: Record<NodeState, string> = {
  done: 'bg-emerald-500 text-white',
  active: 'bg-indigo-500 text-white animate-pulse',
  pending: 'bg-zinc-100 text-zinc-400 border border-zinc-200',
  failed: 'bg-rose-500 text-white',
  hidden: 'opacity-0 pointer-events-none',
};

const LABEL_STYLE: Record<NodeState, string> = {
  done: 'text-zinc-700',
  active: 'text-indigo-700 font-medium',
  pending: 'text-zinc-400',
  failed: 'text-rose-600',
  hidden: 'opacity-0',
};

interface PipelineStripProps {
  task: TaskStatusResponse;
}

export function PipelineStrip({ task }: PipelineStripProps) {
  const states = deriveNodeStates(task);

  return (
    <div className="flex items-center gap-0 overflow-x-auto">
      {ALL_NODES.map((node, i) => {
        const state = states[node.id];
        const isVisible = state !== 'hidden';
        const isLast = i === ALL_NODES.length - 1;
        const nextState = i < ALL_NODES.length - 1 ? states[ALL_NODES[i + 1].id] : 'hidden';

        return (
          <div
            key={node.id}
            className={`flex items-center ${!isVisible ? 'opacity-20' : ''}`}
          >
            <div className="flex flex-col items-center gap-1 min-w-[60px]">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all ${NODE_STYLE[state]}`}
              >
                {NODE_ICON[state]}
              </div>
              <span className={`text-[11px] ${LABEL_STYLE[state]}`}>
                {node.label}
              </span>
            </div>

            {!isLast && (
              <div
                className={`h-px w-6 mx-1 mb-4 transition-colors ${
                  nextState !== 'hidden' && nextState !== 'pending'
                    ? 'bg-zinc-400'
                    : 'bg-zinc-200'
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
