// src/store/auth.js
import { authApi, setAuthToken, clearAuthToken } from "../api/http";

export async function login(idOrEmail, password) {
    const res = await authApi.login({ username: idOrEmail, password });
    if (res?.access_token) {
        setAuthToken(res.access_token, { remember: true });
        return true;
    }
    return false;

}

export async function register({ name, username, password }) {
    const res = await authApi.register({ name, username, password });
    if (res?.access_token) {
        setAuthToken(res.access_token, { remember: true });
        return true;
    }
    return false;
}

export async function checkUsername(username) {
    // GET /api/auth/check-username?username=...
    return await authApi.checkUsername(username);
}

export async function me() {
    return await authApi.me();
}

export async function logout() {
    // 1) 즉시 클라이언트 상태 해제
    clearAuthToken();
    try { window.dispatchEvent(new Event("auth:changed")); } catch { }
    // 2) 서버 세션 정리(실패해도 무시)
    try { await authApi.logout(); } catch { }
    return true;
}