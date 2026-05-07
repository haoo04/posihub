import axios, { type AxiosInstance } from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "";

export const http: AxiosInstance = axios.create({
  baseURL,
  timeout: 15_000,
  headers: {
    "Content-Type": "application/json",
  },
});

http.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err?.response?.data?.detail) {
      err.message = err.response.data.detail;
    }
    return Promise.reject(err);
  }
);
