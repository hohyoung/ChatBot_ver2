// frontend/src/api/http.js
// fetch 래퍼 + 토큰 관리 + 절대 URL 보정 + api/docsApi 네임스페이스 제공

// --- 토큰 메모리/스토리지 ---
let _token = localStorage.getItem("auth_token") || null;
export function setAuthToken(token) {
    _token = token || null;
    if (_token) localStorage.setItem("auth_token", _token);
    else localStorage.removeItem("auth_token");
}
export function getAuthToken() {
    return _token;
}
export function clearAuthToken() {
    _token = null;
    localStorage.removeItem("auth_token");
}

// --- API 베이스 (Vite: VITE_API_BASE) ---
export const API_BASE = (import.meta?.env?.VITE_API_BASE || "").trim();

// --- 절대 URL 보정 ---
export function absolute(url) {
    if (!url) return null;
    const s = String(url);
    if (/^(https?:|data:|blob:)/i.test(s)) return s;
    const base = API_BASE || window.location.origin;
    return base.replace(/\/+$/, "") + "/" + s.replace(/^\/+/, "");
}

// --- 공통 HTTP 호출 ---
async function http(method, url, body, headers) {
    const target =
        API_BASE
            ? API_BASE.replace(/\/+$/, "") + "/" + String(url).replace(/^\/+/, "")
            : String(url);

    const init = {
        method,
        headers: {
            Accept: "application/json",
            ...(body instanceof FormData ? {} : { "Content-Type": "application/json" }),
            ...(headers || {}),
        },
    };

    const t = getAuthToken();
    if (t) init.headers["Authorization"] = `Bearer ${t}`;

    if (body !== undefined && body !== null) {
        init.body = body instanceof FormData ? body : JSON.stringify(body);
    }

    const res = await fetch(target, init);
    if (!res.ok) {
        const text = await res.text().catch(() => "");
        if (res.status === 401) clearAuthToken();
        throw new Error(text || `HTTP ${res.status}`);
    }
    return res.json().catch(() => ({}));
}

// --- 메서드별 래퍼 ---
export const get = (url, headers) => http("GET", url, undefined, headers);
export const post = (url, body, headers) => http("POST", url, body, headers);
export const put = (url, body, headers) => http("PUT", url, body, headers);
export const del = (url, headers) => http("DELETE", url, undefined, headers);

// --- 인증 편의 함수 (store/auth.js 호환) ---
async function login(username_or_email, password) {
    return post("/api/auth/login", { username_or_email, password });
}
async function register({ username, password, password_confirm }) {
    return post("/api/auth/register", { username, password, password_confirm });
}
async function me() {
    return post("/api/auth/me", {});
}
async function checkUsername(username) {
    return get(`/api/auth/check-username?username=${encodeURIComponent(username)}`);
}

// --- 문서 관련 API ---
function toFormData(fileOrFiles, fields = {}) {
    const fd = new FormData();
    const files = Array.isArray(fileOrFiles) || (fileOrFiles && typeof fileOrFiles.length === "number")
        ? Array.from(fileOrFiles)
        : [fileOrFiles].filter(Boolean);
    files.forEach((f) => fd.append("files", f));
    Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
    return fd;
}

async function docsUpload(fileOrFiles, extraFields) {
    const fd = toFormData(fileOrFiles, extraFields);
    return post("/api/docs/upload", fd);
}
async function docsStatus(jobId) {
    return get(`/api/docs/${encodeURIComponent(jobId)}/status`);
}
async function docsMyRaw() {
    return get("/api/docs/my");
}
async function docsMyList() {
    const res = await docsMyRaw();
    // SettingsPage는 res.items를 기대하므로 배열이면 감싸서 맞춰줍니다.
    return Array.isArray(res) ? { items: res } : res;
}
async function docsRemove(docId) {
    return del(`/api/docs/my/${encodeURIComponent(docId)}`);
}

// --- 네임스페이스 export ---
export const api = {
    get, post, put, del, http,
    // 토큰 유틸
    setAuthToken, getAuthToken, clearAuthToken,
    // URL 유틸
    absolute, API_BASE,
    // 인증
    login, register, me, checkUsername,
};

export const docsApi = {
    upload: docsUpload,
    status: docsStatus,
    my: docsMyRaw,        // 기존 이름 유지
    myList: docsMyList,   // ✅ SettingsPage가 호출하는 이름
    remove: docsRemove,   // 기존 이름
    deleteMy: docsRemove, // ✅ SettingsPage가 호출하는 이름
    absolute,
};
