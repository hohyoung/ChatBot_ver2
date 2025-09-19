// src/components/Header/Header.jsx
import React, { useState, useEffect } from "react";
import "./Header.css";
import AuthModal from "../AuthModal/AuthModal.jsx";
import { me, logout } from "../../store/auth";
import { getAuthToken } from "../../api/http";
import { FaBars } from "react-icons/fa";
import { useLocation, useNavigate } from "react-router-dom";

export default function Header({ onToggleSidebar }) {
    const [open, setOpen] = useState(false);
    const [user, setUser] = useState(null);
    const navigate = useNavigate();
    const location = useLocation();

    const refreshUser = async () => {
        try {
            if (!getAuthToken()) {
                setUser(null);
                return;
            }
            const info = await me();
            setUser(info);
        } catch {
            setUser(null);
        }
    };

    useEffect(() => {
        refreshUser();
        // 로그인 상태 변경 감지
        window.addEventListener("auth:changed", refreshUser);
        return () => window.removeEventListener("auth:changed", refreshUser);
    }, []);

    const doLogout = async (e) => {
        e?.preventDefault?.();
        try {
            await logout(); // 토큰 제거 + 이벤트 브로드캐스트(즉시)
        } finally {
            setUser(null);      // 로컬 상태 확정
            await refreshUser(); // 방어적 재조회(토큰 제거 반영)
            if (location.pathname.startsWith("/admin")) {
                navigate("/", { replace: true });
            }
        }
    };

    const displayName = user?.name?.trim?.() || user?.username || "";

    return (
        <header className="hdr">
            <button className="hdr__menu" aria-label="메뉴" onClick={onToggleSidebar}>
                <FaBars />
            </button>

            <div className="hdr__brand">SOOSAN ChatBot</div>
            <div className="hdr__spacer" />

            <div className="hdr__meta">
                {user ? (
                    <>
                        <span className="hdr__hello">
                            안녕하세요 <strong>{displayName}</strong>님. (<span className="mono">@{user.username}</span>)
                        </span>
                        <button type="button" className="btn btn-secondary" onClick={doLogout}>
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
