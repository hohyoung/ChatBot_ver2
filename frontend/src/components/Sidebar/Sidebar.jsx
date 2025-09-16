import React from 'react';
import './Sidebar.css';
import { NavLink } from 'react-router-dom';
import { FaComments, FaUpload, FaCog, FaTimes } from 'react-icons/fa';

export default function Sidebar({ open, onClose }) {
    const linkClass = ({ isActive }) => 'sb__link' + (isActive ? ' is-active' : '');

    return (
        <aside className={'sb ' + (open ? 'is-open' : '')}>
            <button className="sb__close" onClick={onClose} aria-label="사이드바 닫기"><FaTimes /></button>
            <div className="sb__logo">사내 규정</div>
            <nav className="sb__nav">
                <NavLink to="/" className={linkClass} onClick={onClose}>
                    <FaComments /><span>질의응답</span>
                </NavLink>
                <NavLink to="/upload" className={linkClass} onClick={onClose}>
                    <FaUpload /><span>문서 업로드</span>
                </NavLink>
                <NavLink to="/settings" className={linkClass} onClick={onClose}>
                    <FaCog /><span>설정</span>
                </NavLink>
            </nav>
            <div className="sb__foot">/api는 FastAPI로 프록시됩니다.</div>
        </aside>
    );
}
