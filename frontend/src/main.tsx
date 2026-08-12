import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider, App as AntApp } from "antd";
import enUS from "antd/locale/en_US";
import zhCN from "antd/locale/zh_CN";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { antdTheme } from "./theme/antdTheme";
import { ensurePosiTheme } from "./theme/echartsTheme";
import { http } from "./api/client";
import { queryKeys } from "./api/hooks";
import type { Account } from "./api/types";
import { LocaleProvider, useLocale } from "./i18n/LocaleContext";
import "./styles/global.css";

ensurePosiTheme();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

// Prefetch accounts early so position/manual pages can resolve account names
// on first paint instead of flashing "#id" placeholders.
void queryClient.prefetchQuery({
  queryKey: queryKeys.accounts,
  queryFn: async () => (await http.get<Account[]>("/api/v1/accounts")).data,
});

function RootProviders() {
  const { locale } = useLocale();
  return (
    <ConfigProvider
      locale={locale === "zh-CN" ? zhCN : enUS}
      theme={antdTheme}
    >
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LocaleProvider>
      <RootProviders />
    </LocaleProvider>
  </React.StrictMode>
);
