// src/store/auth.js
import { authApi, setAuthToken, clearAuthToken, getAuthToken } from "../api/http";

// 인증 정보 캐싱 (메모리)
let cachedUser = null;
let cachePromise = null;  // 동시 요청 방지

export async function login(idOrEmail, password) {
    const res = await authApi.login({ username: idOrEmail, password });
    if (res?.access_token) {
        setAuthToken(res.access_token, { remember: true });
        cachedUser = null;  // 캐시 초기화
        cachePromise = null;
        return true;
    }
    return false;

}

export async function register({ name, username, password }) {
    const res = await authApi.register({ name, username, password });
    if (res?.access_token) {
        setAuthToken(res.access_token, { remember: true });
        cachedUser = null;  // 캐시 초기화
        cachePromise = null;
        return true;
    }
    return false;
}

export async function checkUsername(username) {
    // GET /api/auth/check-username?username=...
    return await authApi.checkUsername(username);
}

export async function me(forceRefresh = false) {
    // 토큰 없으면 바로 null 반환
    if (!getAuthToken()) {
        cachedUser = null;
        return null;
    }

    // 강제 새로고침이 아니고 캐시가 있으면 캐시 반환
    if (!forceRefresh && cachedUser) {
        return cachedUser;
    }

    // 이미 요청 중이면 해당 Promise 재사용 (동시 요청 방지)
    if (cachePromise) {
        return cachePromise;
    }

    // 새로운 요청
    cachePromise = authApi.me()
        .then(user => {
            cachedUser = user;
            cachePromise = null;
            return user;
        })
        .catch(err => {
            cachedUser = null;
            cachePromise = null;
            throw err;
        });

    return cachePromise;
}

// 캐시 초기화 (로그아웃 등에서 사용)
export function clearAuthCache() {
    cachedUser = null;
    cachePromise = null;
}

export async function logout() {
    // 1) 즉시 클라이언트 상태 해제
    clearAuthToken();
    clearAuthCache();
    try { window.dispatchEvent(new Event("auth:changed")); } catch { }
    // 2) 서버 세션 정리(실패해도 무시)
    try { await authApi.logout(); } catch { }
    return true;
}