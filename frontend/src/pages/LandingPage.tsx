import { Link } from 'react-router-dom';
import ThemeToggle from '../components/ThemeToggle';

const REPO_URL = 'https://github.com/jpaechnatz/poddy';

export default function LandingPage() {
  return (
    <div className="min-h-dvh bg-gradient-to-b from-gray-50 to-white overflow-y-auto overflow-x-hidden fixed inset-0">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 bg-surface/80 backdrop-blur-md border-b border-gray-100 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <img src="/images/logos/logo.webp" alt="Poddy" className="h-8 w-auto" />
              <span className="text-xl font-bold text-gray-900">Poddy</span>
            </div>
            <nav className="hidden md:flex items-center gap-8">
              <a href="#how-it-works" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">
                How it works
              </a>
              <a
                href={REPO_URL}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
              >
                GitHub
              </a>
            </nav>
            <div className="flex items-center gap-3">
              <ThemeToggle />
              <Link to="/login" className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg font-medium transition-colors shadow-sm">
                Sign In
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="pt-32 pb-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 leading-tight mb-6">
            Ad-free podcasts, self-hosted
          </h1>
          <p className="text-lg text-gray-600 mb-8 max-w-3xl mx-auto">
            Poddy removes ads (and, if you like, music breaks) from your podcasts and serves clean RSS feeds
            with chapters, transcripts and summaries that work in any podcast app. This is a private
            instance: sign in to manage your feeds.
          </p>
          <Link
            to="/login"
            className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-8 py-4 rounded-xl font-semibold text-lg transition-colors shadow-lg hover:shadow-xl"
          >
            Sign In
          </Link>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="pt-12 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto space-y-12">
          <div className="text-center">
            <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">How it works</h2>
            <p className="text-lg text-gray-600 max-w-3xl mx-auto">
              Poddy fetches the original feed, finds sponsor blocks using chapters or an LLM, cuts them out
              and gives you a private RSS link for your own podcast app.
            </p>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-gray-100 bg-surface p-6">
              <p className="text-sm font-semibold uppercase tracking-wide text-gray-500 mb-4">Listen anywhere</p>
              <ul className="space-y-3 text-sm text-gray-600">
                <li><strong className="text-gray-900">Apple Podcasts:</strong> Library → Edit → Add Show by URL → paste the Poddy link.</li>
                <li><strong className="text-gray-900">Overcast:</strong> Tap + → Add URL → paste → done.</li>
                <li><strong className="text-gray-900">Pocket Casts:</strong> Discover → Paste RSS Link → Subscribe.</li>
                <li><strong className="text-gray-900">Other players:</strong> Podcast Addict, AntennaPod, Castro, etc. all support "add via URL."</li>
              </ul>
              <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-sm text-amber-900">
                Spotify does not accept custom RSS feeds, so use another podcast app for Poddy links.
              </div>
            </div>
            <div className="rounded-2xl border border-blue-100 bg-blue-50/60 p-6">
              <p className="text-sm font-semibold uppercase tracking-wide text-blue-900 mb-4">Getting started</p>
              <ol className="space-y-3 text-sm text-blue-900/90">
                <li><strong>1.</strong> Sign in.</li>
                <li><strong>2.</strong> Search for a podcast or paste its RSS URL and add it.</li>
                <li><strong>3.</strong> Copy the Poddy RSS link for that feed.</li>
                <li><strong>4.</strong> Paste the link into your podcast app to listen ad-free.</li>
              </ol>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-4 sm:px-6 lg:px-8 border-t border-gray-200">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-2">
              <img src="/images/logos/logo.webp" alt="Poddy" className="h-6 w-auto" />
              <span className="font-semibold text-gray-900">Poddy</span>
            </div>
            <p className="text-sm text-gray-500">
              Open source podcast ad remover, based on{' '}
              <a
                href="https://github.com/podly-pure-podcasts/podly_pure_podcasts"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                Podly Pure Podcasts
              </a>
              .
            </p>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Poddy on GitHub"
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 24 24">
                <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
              </svg>
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
