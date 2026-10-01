import '@testing-library/jest-dom/vitest'

// jsdom has no matchMedia; ThemeProvider reads the system color scheme.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })
}
