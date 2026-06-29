/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * API origin for a split deploy (frontend on Vercel, API on its own host),
   * e.g. https://api.aspora.com. Empty / unset → same-origin relative requests
   * (local dev and the bundled single-origin deploy).
   */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
