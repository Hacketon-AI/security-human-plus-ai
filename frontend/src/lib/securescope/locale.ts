"use client";

import * as React from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type Locale = "en" | "id";

const useLocaleStore = create<{ locale: Locale; setLocale: (locale: Locale) => void }>()(
  persist((set) => ({ locale: "en", setLocale: (locale) => set({ locale }) }), {
    name: "securescope_locale",
    // localStorage can throw (private mode, blocked storage); the default
    // locale still renders, the choice just isn't remembered.
    storage: createJSONStorage(() => localStorage),
  }),
);

/** Current UI locale, kept in sync with `<html lang>` for screen readers. */
export function useLocale(): [Locale, (locale: Locale) => void] {
  const locale = useLocaleStore((state) => state.locale);
  const setLocale = useLocaleStore((state) => state.setLocale);
  React.useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return [locale, setLocale];
}
