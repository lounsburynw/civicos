/// <reference types="vite/client" />
/// <reference types="google.maps" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
