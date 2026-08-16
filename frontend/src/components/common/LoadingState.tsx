interface LoadingStateProps {
  label?: string
}

export default function LoadingState({ label = 'Loading' }: LoadingStateProps) {
  return (
    <div role="status" className="flex flex-col items-center justify-center gap-4 px-6 py-20 text-center">
      <div className="relative h-10 w-10">
        <span className="absolute inset-0 rounded-full border-2 border-line" />
        <span className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-vermilion-500" />
      </div>
      <p className="text-sm tracking-wide text-espresso-light">{label}</p>
    </div>
  )
}
