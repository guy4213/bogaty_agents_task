import { NewTaskForm } from '@/components/form/NewTaskForm';

export default function HomePage() {
  return (
    <div className="max-w-xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-zinc-900 mb-1">New Task</h1>
        <p className="text-sm text-zinc-500">
          Submit a content generation task. Results are available once processing
          completes.
        </p>
      </div>
      <NewTaskForm />
    </div>
  );
}
