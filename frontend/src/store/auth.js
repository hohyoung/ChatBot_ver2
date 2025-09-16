// src/store/auth.js
import { api, setAuthToken, clearAuthToken, getAuthToken } from "../api/http";

export async function login(username_or_email, password) {
    const res = await api.login(username_or_email, password);
    if (res?.access_token) {
        setAuthToken(res.access_token);
        return true;
    }
    return false;
}

export async function register({ username, password, password_confirm }) {
    const res = await api.register({ username, password, password_confirm });
    if (res?.access_token) {
        setAuthToken(res.access_token);
        return true;
    }
    return false;
}

export async function me() {
    const token = getAuthToken();
    if (!token) return null;
    try {
        return await api.me();
    } catch {
        clearAuthToken();
        return null;
    }
}

export function logout() {
    clearAuthToken();
}

export async function checkUsername(username) {
    return api.checkUsername(username); // { available: boolean }
}
