import React from 'react';
import Header from './components/Header.jsx';
import Sidebar from './components/Sidebar.jsx';
import QueryPage from './pages/QueryPage.jsx';
import UploadPage from './pages/UploadPage.jsx';
import SettingsPage from './pages/SettingsPage.jsx';
import { Routes, Route } from 'react-router-dom';

export default function App() {
  return (
    <div className="app">
      <Header />
      <div className="shell">
        <Sidebar />
        <main className="main">
          <Routes>
            <Route path="/" element={<QueryPage />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
