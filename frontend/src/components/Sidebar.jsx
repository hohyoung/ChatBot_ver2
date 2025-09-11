import React from 'react';
import { NavLink } from 'react-router-dom';

export default function Sidebar() {
    const linkClass = ({ isActive }) => isActive ? 'active' : '';
    return (
        <div className="sidebar">
            <div className="nav">
                <NavLink to="/" className={linkClass}>질의</NavLink>
                <NavLink to="/upload" className={linkClass}>문서 업로드</NavLink>
                <NavLink to="/settings" className={linkClass}>설정</NavLink>
            </div>
            <div className="small">/api는 FastAPI로 프록시됩니다.</div>
        </div>
    );
}
