import React, { useEffect, useState } from "react";
import "./Sidebar.css";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { FaComments, FaUpload, FaCog, FaTools, FaTimes } from "react-icons/fa";
import { authApi, getAuthToken } from "../../api/http";

export default function Sidebar({ open, onClose }) {
    const [me, setMe] = useState(null);
    const isAdmin = Number(me?.security_level) === 1;

    const navigate = useNavigate();
    const location = useLocation();

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

    // ⬇ 권한이 더 이상 관리자 아닐 때 /admin에 있다면 "/"로 이동
    useEffect(() => {
        if (location.pathname.startsWith("/admin") && !isAdmin) {
            navigate("/", { replace: true });
        }
    }, [isAdmin, location.pathname, navigate]);

    return (
        <aside className={`sb ${open ? "is-open" : ""}`}>
            <div className="sb__logo">메뉴</div>

            <button className="sb__close" onClick={onClose} aria-label="닫기">
                <FaTimes />
            </button>

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
