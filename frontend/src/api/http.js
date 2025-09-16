// 작은 fetch 래퍼 (에러 처리 포함)

// 토큰 메모리/스토리지
let _token = localStorage.getItem("auth_token") || null;
export function setAuthToken(token) {
    _token = token || null;
    if (_token) localStorage.setItem("auth_token", _token);
    else localStorage.removeItem("auth_token");
}
export function getAuthToken() {
    return _token;
}

// API 베이스 (Vite 환경변수 사용 가능)
const API_BASE = import.meta?.env?.VITE_API_BASE || "";

// 공통 HTTP 호출
async function http(method, url, body, headers) {
    const init = {
        method,
        headers: {
            "Accept": "application/json",
            ...(body instanceof FormData ? {} : { "Content-Type": "application/json" }),
            ...(headers || {}),
        },
    };

    // Authorization 헤더
    const t = getAuthToken();
    if (t) init.headers["Authorization"] = `Bearer ${t}`;

    // 바디
    if (body !== undefined && body !== null) {
        init.body = body instanceof FormData ? body : JSON.stringify(body);
    }

    const res = await fetch(API_BASE + url, init);
    if (!res.ok) {
        let text = await res.text().catch(() => "");
        // 401이면 토큰 제거(선택)
        if (res.status === 401) setAuthToken(null);
        throw new Error(text || `HTTP ${res.status}`);
    }
    return res.json().catch(() => ({}));
}

export const get = (url, headers) => http("GET", url, undefined, headers);
export const post = (url, body, headers) => http("POST", url, body, headers);
