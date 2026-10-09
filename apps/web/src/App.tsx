import { ModeToggle } from '@/shared/theme/mode-toggle'

function App() {
  return (
    <main className="relative grid min-h-svh place-content-center justify-items-center gap-2 p-6 text-center">
      <div className="absolute inset-e-4 top-4">
        <ModeToggle />
      </div>
      <img src="/favicon.svg" alt="" className="size-24" />
      <h1 className="text-4xl font-bold">PushTalk</h1>
      <p className="text-muted-foreground">Walkie-talkie voice channels. Hold to talk, release to send.</p>
    </main>
  )
}

export default App
