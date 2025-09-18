import React, { useState, useEffect } from "react";
import "./Header.css";
import AuthModal from "../AuthModal/AuthModal.jsx";
import { me, logout } from "../../store/auth";
import { getAuthToken } from "../../api/http";

export default function Header() {
    const [open, setOpen] = useState(false);
    const [user, setUser] = useState(null);

    const refreshUser = async () => {
        try {
            if (!getAuthToken()) { setUser(null); return; }
            const info = await me();
            setUser(info);
        } catch { setUser(null); }
    };

    useEffect(() => { refreshUser(); }, []);

    return (
        <header className="hdr">
            {/* (선택) 모바일 햄버거 버튼 — 사이드바 토글 연결 시 사용 */}
            <button className="hdr__menu" aria-label="메뉴">☰</button>

            <div className="hdr__brand">SSB Chat</div>
            <div className="hdr__spacer" />

            <div className="hdr__meta">
                {user ? (
                    <>
                        <span className="hdr__metaText">{user.username} (Lv.{user.security_level})</span>
                        <button
                            className="btn"
                            onClick={() => { logout(); setUser(null); }}
                        >
                            로그아웃
                        </button>
                    </>
                ) : (
                    <button className="btn btn-primary" onClick={() => setOpen(true)}>
                        로그인
                    </button>
                )}
            </div>

            <AuthModal open={open} onClose={() => setOpen(false)} onLoggedIn={refreshUser} />
        </header>
    );
}
