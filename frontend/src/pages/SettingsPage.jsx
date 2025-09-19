import React, { useEffect, useState } from "react";
import "./SettingPage.css";
import { docsApi } from "../api/http";
import { me as fetchMe } from "../store/auth";
import { FaLock } from "react-icons/fa";

import ProfileSection from "../components/Settings/ProfileSection.jsx";
import MyDocsSection from "../components/Settings/MyDocsSection.jsx";

/** 상단 카드 스위처 */
function SettingsSwitcher({ value, onChange }) {
  const cards = [
    { key: "profile", title: "내 정보", desc: "이름/아이디/이메일/비밀번호 수정" },
    { key: "docs", title: "내 문서", desc: "내가 업로드한 문서 목록/삭제" },
  ];
  return (
    <div className="settings__switcher">
      {cards.map((c) => (
        <button
          key={c.key}
          onClick={() => onChange(c.key)}
          className={"settings__card" + (value === c.key ? " is-active" : "")}
        >
          <div className="settings__card_ttl">{c.title}</div>
          <div className="settings__card_desc">{c.desc}</div>
        </button>
      ))}
    </div>
  );
}

export default function SettingsPage() {
  const [user, setUser] = useState(null);
  const [err, setErr] = useState("");
  const [mode, setMode] = useState("profile");
  const isLoggedIn = !!user;

  useEffect(() => {
    (async () => {
      try { setUser(await fetchMe()); } catch { setUser(null); }
    })();

    const onAuthChanged = () => window.location.reload();
    const onStorage = (e) => { if (e.key === "auth_token") onAuthChanged(); };
    window.addEventListener("auth:changed", onAuthChanged);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("auth:changed", onAuthChanged);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return (
    <div className="settings-page">
      <h2 className="page-title">설정</h2>
      <p className="page-subtitle">계정/문서 등 개인 설정을 관리합니다.</p>

      <SettingsSwitcher value={mode} onChange={setMode} />

      {!isLoggedIn && (
        <div className="banner guard-banner">
          <FaLock />
          <div>
            <strong>로그인이 필요합니다.</strong>
            <div>로그인 후 설정을 변경할 수 있어요.</div>
          </div>
        </div>
      )}
      {err && <div className="banner error">{err}</div>}

      {/* ⬇️ 바깥 컨테이너는 ‘문구(타이틀)’ 없이 섹션 컴포넌트만 렌더 */}
      <section className="section">
        <div className={`card table-card ${!isLoggedIn ? "is-disabled" : ""}`}>
          {!isLoggedIn && (
            <div className="blocked-overlay">
              <FaLock />
              <div className="blocked-text">로그인 후 이용 가능합니다</div>
            </div>
          )}

          {mode === "profile" ? (
            <ProfileSection
              user={user}
              onUserRefresh={async () => {
                try { const u = await fetchMe(); setUser(u || null); } catch { }
              }}
            />
          ) : (
            <MyDocsSection isLoggedIn={isLoggedIn} docsApi={docsApi} />
          )}
        </div>
      </section>
    </div>
  );
}
