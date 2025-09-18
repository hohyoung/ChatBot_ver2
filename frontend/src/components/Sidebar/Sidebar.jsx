import React, { useEffect, useState } from "react";
import "./Sidebar.css";
import { NavLink } from "react-router-dom";
import { FaComments, FaUpload, FaCog, FaTools, FaTimes } from "react-icons/fa";
import { authApi, getAuthToken } from "../../api/http";

export default function Sidebar({ open, onClose }) {
    const [me, setMe] = useState(null);
    const isAdmin = Number(me?.security_level) === 1;

    const linkClass = ({ isActive }) => "sb__link" + (isActive ? " is-active" : "");

    async function refreshMe() {
        if (!getAuthToken()) {
            setMe(null);
            return;
        }
        try {
            const info = await authApi.me();
            setMe(info || null);
        } catch {
            setMe(null);
        }
    }

    useEffect(() => {
        refreshMe();

        const onAuthChanged = () => refreshMe();
        const onStorage = (e) => {
            if (e.key === "auth_token") onAuthChanged();
        };

        window.addEventListener("auth:changed", onAuthChanged);
        window.addEventListener("storage", onStorage);
        window.addEventListener("focus", onAuthChanged);
        return () => {
            window.removeEventListener("auth:changed", onAuthChanged);
            window.removeEventListener("storage", onStorage);
            window.removeEventListener("focus", onAuthChanged);
        };
    }, []);

    return (
        // ⬇⬇ CSS와 일치: .sb + (open 시) .is-open
        <aside className={`sb ${open ? "is-open" : ""}`}>
            {/* 헤더 영역: CSS엔 sb__header가 없고 sb__logo만 있음 */}
            <div className="sb__logo">메뉴</div>

            {/* 모바일에서만 보이는 닫기 버튼 (CSS: .sb__close) */}
            <button className="sb__close" onClick={onClose} aria-label="닫기">
                <FaTimes />
            </button>

            {/* 네비게이션 (CSS: .sb__nav / .sb__link / .sb__link.is-active) */}
            <nav className="sb__nav">
                <NavLink to="/" className={linkClass} onClick={onClose}>
                    <FaComments /> 대화
                </NavLink>
                <NavLink to="/upload" className={linkClass} onClick={onClose}>
                    <FaUpload /> 업로드
                </NavLink>
                <NavLink to="/settings" className={linkClass} onClick={onClose}>
                    <FaCog /> 설정
                </NavLink>
                {isAdmin && (
                    <NavLink to="/admin" className={linkClass} onClick={onClose}>
                        <FaTools /> 관리자 설정
                    </NavLink>
                )}
            </nav>
            <div className="sb__foot" />
        </aside>
    );
}
