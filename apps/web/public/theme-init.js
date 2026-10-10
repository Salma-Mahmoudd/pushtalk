// Applies the saved theme before the first paint, so dark mode does not flash white.
// Loaded as a file (not inline) so the Content-Security-Policy can allow only same-origin scripts.
try {
  const theme = localStorage.getItem('theme') ?? 'system'
  const dark = theme === 'dark' || (theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
} catch {
  // Storage unavailable (e.g. blocked cookies): the provider falls back to the system theme.
}
