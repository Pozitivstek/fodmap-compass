// Обращения к API. Каждый запрос подписан initData из Telegram.
const tg = window.Telegram?.WebApp;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body, form } = {}) {
  const headers = { "X-Telegram-Init-Data": tg?.initData || "" };
  let payload;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, { method, headers, body: payload });
  } catch {
    throw new ApiError("Нет связи с сервером. Проверьте интернет.", 0);
  }
  const type = response.headers.get("content-type") || "";
  if (!response.ok) {
    let detail = "Ошибка сервера";
    if (type.includes("json")) {
      const data = await response.json().catch(() => ({}));
      detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail || detail;
    }
    throw new ApiError(detail, response.status);
  }
  if (type.includes("application/pdf")) return response.blob();
  return type.includes("json") ? response.json() : response.text();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
  put: (path, body) => request(path, { method: "PUT", body }),
  patch: (path, body) => request(path, { method: "PATCH", body }),
  del: (path) => request(path, { method: "DELETE" }),
  upload: (path, form) => request(path, { method: "POST", form }),
};

export const q = (params) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : "";
};
