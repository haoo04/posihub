import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { messages, type Locale } from "./messages";
import { setDateLocale } from "@/utils/format";

const STORAGE_KEY = "posihub-locale";
const DEFAULT_LOCALE: Locale = "zh-CN";

type InterpolationValues = Record<string, string | number>;

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, values?: InterpolationValues) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

function isLocale(value: string | null): value is Locale {
  return value === "zh-CN" || value === "en";
}

function readInitialLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return isLocale(stored) ? stored : DEFAULT_LOCALE;
}

function resolveMessage(locale: Locale, key: string): string {
  const path = key.split(".");
  let cursor: unknown = messages[locale];

  for (const segment of path) {
    if (!cursor || typeof cursor !== "object" || !(segment in cursor)) {
      cursor = undefined;
      break;
    }
    cursor = (cursor as Record<string, unknown>)[segment];
  }

  if (typeof cursor === "string") return cursor;
  if (locale !== DEFAULT_LOCALE) return resolveMessage(DEFAULT_LOCALE, key);
  return key;
}

function interpolate(template: string, values?: InterpolationValues): string {
  if (!values) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
    String(values[name] ?? "")
  );
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readInitialLocale);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
    window.localStorage.setItem(STORAGE_KEY, nextLocale);
  }, []);

  useEffect(() => {
    setDateLocale(locale);
    document.documentElement.lang = locale;
    document.title = messages[locale].appTitle;
  }, [locale]);

  const t = useCallback(
    (key: string, values?: InterpolationValues) =>
      interpolate(resolveMessage(locale, key), values),
    [locale]
  );

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t,
    }),
    [locale, setLocale, t]
  );

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error("useLocale must be used within LocaleProvider");
  }
  return context;
}
