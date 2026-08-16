import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-6 py-32 text-center lg:px-10">
      <p className="eyebrow mb-4">404</p>
      <h1 className="font-display text-4xl text-espresso">This page could not be found.</h1>
      <p className="mt-4 text-sm text-espresso-light">
        The page you're looking for doesn't exist, or may have moved.
      </p>
      <Link to="/" className="btn-primary mt-8">
        Return Home
      </Link>
    </div>
  )
}
