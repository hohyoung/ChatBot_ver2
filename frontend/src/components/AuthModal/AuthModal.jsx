// src/components/auth/AuthModal.jsx
import React, { useState } from "react";
import "./AuthModal.css";
import { authApi, setAuthToken } from "../../api/http";

export default function AuthModal({ open, onClose, onLoggedIn }) {
    const [tab, setTab] = useState("login"); // 'login' | 'signup'
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState("");

    // login
    const [usernameOrEmail, setUsernameOrEmail] = useState("");
    const [pw, setPw] = useState("");

    // signup
    const [username, setUsername] = useState("");
    const [pw1, setPw1] = useState("");
    const [pw2, setPw2] = useState("");
    const [nameChecked, setNameChecked] = useState(null); // true/false
    const [name, setName] = useState("");

    if (!open) return null;

    const onBackdropClick = (e) => {
        
        return;
    };


    async function handleLogin(e) {
        e?.preventDefault();
        setLoading(true);
        setErr("");
        try {
            // 현재 백엔드는 username 로그인만 지원
            const res = await authApi.login({ username: usernameOrEmail.trim(), password: pw });
            if (!res?.access_token) {
                setErr("아이디 또는 비밀번호가 올바르지 않습니다.");
                return;
            }
            setAuthToken(res.access_token, { remember: true });
            await authApi.me(); // 토큰 확인 겸 사용자 정보 초기화
            window.dispatchEvent(new Event("auth:changed"));
            onLoggedIn?.();
            onClose?.();
        } catch (e2) {
            setErr(String(e2?.message || e2));
        } finally {
            setLoading(false);
        }
    }

    async function onCheckUsername() {
        setErr("");
        if ((username || "").trim().length < 3) {
            setErr("아이디는 3자 이상이어야 합니다.");
            return;
        }
        const { available } = await authApi.checkUsername(username.trim());
        setNameChecked(!!available);
        if (!available) setErr("이미 사용 중인 아이디입니다.");
    }

    async function handleRegister(e) {
        e?.preventDefault();
        setLoading(true);
        setErr("");

        try {
            const trimmedName = (name || "").trim();
            const trimmedUsername = (username || "").trim();

            if (!trimmedName) {
                setErr("이름을 입력하세요.");
                return;
            }
            if (pw1 !== pw2) {
                setErr("비밀번호 확인이 일치하지 않습니다.");
                return;
            }
            if ((pw1 || "").length < 8) {
                setErr("비밀번호는 8자 이상이어야 합니다.");
                return;
            }
            if (!nameChecked) {
                setErr("아이디 중복 확인을 먼저 해주세요.");
                return;
            }

            // 이메일 없이 회원가입 허용
            const res = await authApi.register({
                name: trimmedName,
                username: trimmedUsername,
                password: pw1,
            });
            if (!res?.access_token) {
                setErr("회원가입 실패");
                return;
            }
            setAuthToken(res.access_token, { remember: true });
            await authApi.me();
            window.dispatchEvent(new Event("auth:changed"));
            onLoggedIn?.();
            onClose?.();
        } catch (e2) {
            setErr(e2?.message || "회원가입 실패");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="authmodal__backdrop" onClick={onBackdropClick}>
            <div className="authmodal__modal">
                <div className="authmodal__header">
                    <div className="title">계정</div>
                    <button className="btn btn-ghost" onClick={onClose} aria-label="닫기">
                        닫기
                    </button>
                </div>

                <div className="authmodal__body">
                    <div className="tabs">
                        <button
                            className={`tab ${tab === "login" ? "active" : ""}`}
                            onClick={() => setTab("login")}
                            type="button"
                        >
                            로그인
                        </button>
                        <button
                            className={`tab ${tab === "signup" ? "active" : ""}`}
                            onClick={() => setTab("signup")}
                            type="button"
                        >
                            회원가입
                        </button>
                    </div>

                    {tab === "login" ? (
                        <form className="form" onSubmit={handleLogin}>
                            <div className="form-row">
                                <label>아이디</label>
                                <input
                                    className="input"
                                    placeholder="username"
                                    value={usernameOrEmail}
                                    onChange={(e) => setUsernameOrEmail(e.target.value)}
                                />
                            </div>

                            <div className="form-row">
                                <label>비밀번호</label>
                                <input
                                    className="input"
                                    type="password"
                                    placeholder="비밀번호"
                                    value={pw}
                                    onChange={(e) => setPw(e.target.value)}
                                />
                            </div>

                            {err && <div className="error">{err}</div>}

                            <div className="form-actions">
                                <button className="btn btn-primary" disabled={loading} type="submit">
                                    로그인
                                </button>
                                
                            </div>
                        </form>
                    ) : (
                        <form className="form" onSubmit={handleRegister}>
                            <div className="form-row two">
                                <div className="col">
                                    <label>아이디(3~32자)</label>
                                    <input
                                        className="input"
                                        value={username}
                                        onChange={(e) => {
                                            setUsername(e.target.value);
                                            setNameChecked(null);
                                        }}
                                        placeholder="아이디"
                                    />
                                    {nameChecked === true && (
                                        <div className="help">사용 가능한 아이디입니다.</div>
                                    )}
                                    {nameChecked === false && (
                                        <div className="error">이미 사용 중인 아이디입니다.</div>
                                    )}
                                </div>
                                <div className="col end">
                                    <label>&nbsp;</label>
                                    <button
                                        type="button"
                                        className="btn btn-ghost"
                                        onClick={onCheckUsername}
                                    >
                                        중복확인
                                    </button>
                                </div>
                            </div>

                            <div className="form-row">
                                <label htmlFor="name">이름</label>
                                <input
                                    id="name"
                                    type="text"
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    placeholder="홍길동"
                                    autoComplete="name"
                                />
                            </div>

                            <div className="form-row">
                                <label>비밀번호(8자 이상)</label>
                                <input
                                    className="input"
                                    type="password"
                                    value={pw1}
                                    onChange={(e) => setPw1(e.target.value)}
                                />
                            </div>

                            <div className="form-row">
                                <label>비밀번호 확인</label>
                                <input
                                    className="input"
                                    type="password"
                                    value={pw2}
                                    onChange={(e) => setPw2(e.target.value)}
                                />
                            </div>

                            {err && <div className="error">{err}</div>}

                            <div className="form-actions">
                                <button className="btn btn-primary" disabled={loading} type="submit">
                                    가입하기
                                </button>
                                
                            </div>
                        </form>
                    )}
                </div>

                
            </div>
        </div>
    );
}
