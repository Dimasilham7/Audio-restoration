import type { DesktopApi } from "./index";

declare global {
  interface Window {
    audiorestorer: DesktopApi;
  }
}

export {};
