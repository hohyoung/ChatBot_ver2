// ======================================================
// Base settings
// ======================================================

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

// 서버 연결 오류 메시지
export const SERVER_ERROR_MESSAGE = {
    title: "서버에 문제가 발생했습니다",
    detail: "귀하의 문제가 아니니 걱정하지 마세요. 문제가 지속될 경우 DI팀 안호형 실습생에게 문의 바랍니다.",
    contact: "hh.ahn@soosan.co.kr, 010-2647-1625"
};

// 서버 연결 오류인지 확인 (500 에러 또는 네트워크 오류)
export function isServerError(error) {
    if (!error) return false;
    // 네트워크 오류 (fetch 실패)
    if (error.message === 'Failed to fetch' || error.name === 'TypeError') return true;
    // 500번대 서버 오류
    if (error.status >= 500) return true;
    return false;
}
// 💡 '/api'를 제거하여 정적 파일(문서, 이미지 등)을 위한 기본 주소를 만듭니다.
const STATIC_BASE = (import.meta.env.VITE_API_BASE || "").replace("/api", "");

export { API_BASE, STATIC_BASE }; // 💡 STATIC_BASE도 export 해줍니다.
const TOKEN_KEY = "auth_token";

// ------------------------------------------------------
// small helpers
// ------------------------------------------------------
function toQuery(params) {
    if (!params) return "";
    const usp = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
        if (v === undefined || v === null) return;
        if (Array.isArray(v)) v.forEach((item) => usp.append(k, String(item)));
        else usp.set(k, String(v));
    });
    const qs = usp.toString();
    return qs ? `?${qs}` : "";
}

async function parseJsonSafe(res) {
    const text = await res.text();
    try {
        return text ? JSON.parse(text) : null;
    } catch {
        return text || null;
    }
}

function getAuthToken() {
    return (
        localStorage.getItem(TOKEN_KEY) ||
        sessionStorage.getItem(TOKEN_KEY) ||
        ""
    );
}
function setAuthToken(token, { remember = true } = {}) {
    if (!token) return;
    if (remember) {
        localStorage.setItem(TOKEN_KEY, token);
        sessionStorage.removeItem(TOKEN_KEY);
    } else {
        sessionStorage.setItem(TOKEN_KEY, token);
        localStorage.removeItem(TOKEN_KEY);
    }
}
function clearAuthToken() {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
}

async function http(method, path, body, opts = {}) {
    // 1) URL + 쿼리
    let url = path.startsWith("http") ? path : `${API_BASE}${path}`;
    if (opts && opts.params) url += toQuery(opts.params);

    // 2) Authorization 자동 주입
    const headers = new Headers(opts.headers || {});
    const token = getAuthToken();
    if (token && !headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${token}`);
    }
    const isForm = body instanceof FormData;

    if (!isForm) {
        if (!headers.has("Content-Type")) {
            headers.set("Content-Type", "application/json; charset=utf-8");
        }
    } else {
        // FormData일 때는 브라우저가 Content-Type 설정
        headers.delete("Content-Type");
    }

    const fetchOpts = {
        method,
        headers,
        credentials: "include",
        ...opts,
        body: isForm ? body : body != null ? JSON.stringify(body) : undefined,
    };

    const res = await fetch(url, fetchOpts);

    if (res.ok) {
        if (res.status === 204) return null;
        const ct = res.headers.get("content-type") || "";
        if (ct.includes("application/json")) return await res.json();
        return await parseJsonSafe(res);  
    }

    if (res.status === 401) {
        // 로그인 요청 자체에서 401이 발생한 경우는 토큰 클리어/이벤트 발생 제외
        // (로그인 실패 시 모달이 닫히는 버그 방지)
        const isLoginRequest = path.includes('/auth/login');
        if (!isLoginRequest) {
            try {
                clearAuthToken();
            } catch { }
            try {
                window.dispatchEvent(new Event("auth:changed"));
            } catch { }
        }
    }

    const data = await parseJsonSafe(res);
    const detail =
        (data && (data.detail || data.message)) ||
        `HTTP ${res.status} ${res.statusText}`;
    const err = new Error(typeof detail === "string" ? detail : "Request failed");
    err.status = res.status;
    err.data = data;
    throw err;
}

// ------------------------------------------------------
// Shorthands
// ------------------------------------------------------
export const get = (url, opts) => http("GET", url, undefined, opts);
export const post = (url, data, opts) => http("POST", url, data, opts);
export const put = (url, data, opts) => http("PUT", url, data, opts);
export const del = (url, opts) => http("DELETE", url, undefined, opts);
const patch = (path, body, opts) => http("PATCH", path, body, opts);
const postForm = (path, formData, opts) => http("POST", path, formData, opts);

// ======================================================
// Domain APIs
// ======================================================

// --------------------------
// Auth
// --------------------------
export const authApi = {
    // 로그인: { username, password } → { access_token, token_type }
    login: ({ username, password }) =>
        post("/auth/login", { username, password }),

    // 로그아웃(백엔드 ok 반환, 프론트에서 토큰 삭제)
    logout: async () => {
        try { await post("/auth/logout", {}); } catch { }
        clearAuthToken();
        try { window.dispatchEvent(new Event("auth:changed")); } catch { }
        return { ok: true };
    },

    // 현재 사용자 조회(POST /auth/me, Authorization 자동 부착)
    me: () => {
        const token =
            localStorage.getItem("auth_token") ||
            sessionStorage.getItem("auth_token");
        // 토큰 없으면 굳이 요청하지 않음 → 초기 401 사라짐
        if (!token) return Promise.resolve(null);
        return post("/auth/me", {});
    },
    // 아이디 중복 확인: GET /auth/check-username?username=foo
    checkUsername: (username) =>
        get("/auth/check-username", { params: { username } }),

    // 회원가입 (이메일 검증 없이: name/username/password만)
    register: ({ name, username, password }) =>
        post("/auth/register", { name, username, password }),

    // (보류) 비밀번호 변경: 나중에 라우터 열리면 사용
    changePassword: ({ current_password, new_password, new_password_confirm }) =>
        patch("/auth/password", {
            current_password,
            new_password,
            new_password_confirm,
        }),

    updateMe: (patchDoc) => patch("/auth/me", patchDoc),
};

// --------------------------
// Documents (사용자 영역)
// --------------------------
export const docsApi = {
    upload: (formData) => postForm("/docs/upload", formData),
    status: (job_id) => get(`/docs/${encodeURIComponent(job_id)}/status`),
    // 현재 사용자의 진행 중인 업로드 작업 조회
    activeJobs: () => get("/docs/active-jobs"),
    myList: () => get("/docs/my"),
    remove: (doc_id) => del(`/docs/my/${encodeURIComponent(doc_id)}`),
    locate: ({ doc_id, page }) =>
        get("/docs/locate", { params: { doc_id, page } }),

    // P0-4: 문서 검색 및 통계
    search: ({ keyword, tags, doc_type, owner_username, visibility, year, limit, offset }) =>
        get("/docs/search", {
            params: {
                keyword,
                tags, // 콤마 구분 문자열
                doc_type,
                owner_username,
                visibility,
                year,
                limit,
                offset,
            },
        }),
    stats: () => get("/docs/stats"),

    // 챗봇 사서: 자연어 쿼리 → 필터 파라미터 추출
    librarian: (query) => post("/docs/librarian", { query }),
};

// --------------------------
// Admin (관리자 전용) — 필요 시 라우터 붙여 사용
// --------------------------
export const adminApi = {
    users: {
        list: () => get("/admin/users"),
        create: ({ name, username, password, security_level, email, is_active }) =>
            post("/admin/users", {
                name,
                username,
                password,
                security_level,
                email,
                is_active,
            }),
        update: (id, patchDoc) =>
            patch(`/admin/users/${encodeURIComponent(id)}`, patchDoc),
        remove: (id) => del(`/admin/users/${encodeURIComponent(id)}`),
    },
    docs: {
        list: () => get("/admin/docs"),
        remove: (doc_id) => del(`/admin/docs/${encodeURIComponent(doc_id)}`),
        // 청크 조회 (관리자 전용)
        chunks: (doc_id) => get(`/admin/docs/${encodeURIComponent(doc_id)}/chunks`),
    },
};

// --------------------------
// Health
// --------------------------
export const healthApi = {
    ping: () => get("/health/ping"),
};

// ======================================================
// Token helpers export (다른 모듈에서 사용)
// ======================================================
export { getAuthToken, setAuthToken, clearAuthToken };

// (optional) legacy bundle
export const api = { http, get, post, put, patch, del, postForm };
export default { api, authApi, docsApi, adminApi, healthApi };
