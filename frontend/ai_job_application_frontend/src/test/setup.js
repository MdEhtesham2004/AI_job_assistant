import '@testing-library/jest-dom/vitest'
import { configure } from '@testing-library/react'

// findBy*/waitFor default to 1 s; page tests chain several mocked requests and were
// flaky on a busy machine (e.g. while the backend suite runs). 5 s keeps them stable.
configure({ asyncUtilTimeout: 5000 })

// jsdom has no matchMedia; ThemeProvider reads the system color scheme.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })
}
