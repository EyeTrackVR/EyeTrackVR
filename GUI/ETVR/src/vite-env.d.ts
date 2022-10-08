/// <reference types="vite/client" />

interface Config {
    LOG: any
    LOG_LEVEL: any
    CONFIG: any
    SEP: string
}

interface ImportMeta {
    config: Config;
}