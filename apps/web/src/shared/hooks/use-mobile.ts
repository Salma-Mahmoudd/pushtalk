import { useSyncExternalStore } from 'react'

const MOBILE_QUERY = '(max-width: 767px)'

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(MOBILE_QUERY)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}

/** True below 768 px; follows window resizes without an extra render. */
export function useIsMobile(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia(MOBILE_QUERY).matches)
}
