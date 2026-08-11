/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CHAT_API_URL?: string;
  readonly VITE_ENABLE_DEV_CUSTOMER_HEADER?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
