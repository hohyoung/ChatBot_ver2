import React, { useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Header from './components/Header/Header.jsx';
import Sidebar from './components/Sidebar/Sidebar.jsx';
import QueryPage from './pages/QueryPage.jsx';
import UploadPage from './pages/UploadPage.jsx';
import SettingsPage from './pages/SettingsPage.jsx';
import AdminSettingsPage from './pages/AdminSettingsPage.jsx';
import './index.css';

export default function App() {
  const [open, setOpen] = useState(false); // 모바일 사이드바

  return (
    <div className="app" style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header onToggleSidebar={() => setOpen(v => !v)} />
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '240px 1fr', minHeight: 0 }}>
        <Sidebar open={open} onClose={() => setOpen(false)} />
        <main style={{ padding: 16, overflow: 'auto' }}>
          <Routes>
            <Route path="/" element={<QueryPage />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/admin" element={<AdminSettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
