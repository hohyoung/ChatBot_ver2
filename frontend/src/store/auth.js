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
    try { await authApi.logout(); } finally { clearAuthToken(); }
    return true;
}
