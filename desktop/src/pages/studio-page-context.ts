import { inject, type InjectionKey } from "vue";

export type StudioPageContext = Record<string, any>;

export const studioPageContextKey: InjectionKey<StudioPageContext> = Symbol(
  "studio-page-context",
);

export function useStudioPageContext() {
  const context = inject(studioPageContextKey);
  if (!context) throw new Error("Studio page context is unavailable.");
  return context;
}
