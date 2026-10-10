// Opus is preferred (Chrome, Firefox); Safari records AAC in MP4. The server normalises all.
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4']

export interface Recording {
  blob: Blob
  durationMs: number
}

export class MicrophoneBlockedError extends Error {
  constructor() {
    super('Microphone access is blocked. Allow it in the browser to talk.')
    this.name = 'MicrophoneBlockedError'
  }
}

/** One recording at a time; the microphone is released as soon as it stops. */
export class Recorder {
  private mediaRecorder: MediaRecorder | null = null
  private chunks: Blob[] = []
  private startedAt = 0

  get recording(): boolean {
    return this.mediaRecorder?.state === 'recording'
  }

  async start(): Promise<void> {
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'NotAllowedError') throw new MicrophoneBlockedError()
      throw error
    }
    const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type))
    const recorder = new MediaRecorder(stream, { mimeType, audioBitsPerSecond: 32_000 })
    this.chunks = []
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data)
    }
    this.mediaRecorder = recorder
    recorder.start()
    this.startedAt = performance.now()
  }

  /** Stops and returns the recording (its length is measured here; the server measures again). */
  stop(): Promise<Recording> {
    const recorder = this.mediaRecorder
    if (!recorder) return Promise.reject(new Error('not recording'))
    return new Promise((resolve) => {
      recorder.onstop = () => {
        resolve({
          blob: new Blob(this.chunks, { type: recorder.mimeType }),
          durationMs: performance.now() - this.startedAt,
        })
        this.release()
      }
      recorder.stop()
    })
  }

  cancel(): void {
    if (this.mediaRecorder?.state === 'recording') {
      this.mediaRecorder.onstop = () => this.release()
      this.mediaRecorder.stop()
    } else {
      this.release()
    }
  }

  private release(): void {
    this.mediaRecorder?.stream.getTracks().forEach((track) => track.stop())
    this.mediaRecorder = null
    this.chunks = []
  }
}
