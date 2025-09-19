import React, { useMemo, useState } from "react";
import { authApi } from "../../api/http";
import { FaEdit, FaSave, FaTimes } from "react-icons/fa";

/** 보기/편집 토글형 - 내 정보 섹션 */
export default function ProfileSection({ user, onUserRefresh }) {
    const viewing = !user;
    const [editing, setEditing] = useState(false);
    const [saving, setSaving] = useState(false);
    const [msg, setMsg] = useState("");

    const [form, setForm] = useState(() => ({
        name: user?.name || "",
        username: user?.username || "",
        email: user?.email || "",
        current_password: "",
        new_password: "",
        new_password_confirm: "",
    }));

    // user 바뀌면 폼 초기화
    useMemo(() => {
        setForm({
            name: user?.name || "",
            username: user?.username || "",
            email: user?.email || "",
            current_password: "",
            new_password: "",
            new_password_confirm: "",
        });
        setEditing(false);
        setMsg("");
    }, [user]);

    const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

    async function onSave() {
        if (!editing) return;
        setSaving(true);
        setMsg("");
        try {
            const patch = {};
            if (form.name !== (user?.name || "")) patch.name = form.name.trim();
            if (form.username !== (user?.username || "")) patch.username = form.username.trim();
            if (form.email !== (user?.email || "")) patch.email = form.email.trim();
            if (Object.keys(patch).length) await authApi.updateMe(patch);

            const touchedPwd = form.current_password || form.new_password || form.new_password_confirm;
            if (touchedPwd) {
                if (!form.current_password || !form.new_password || !form.new_password_confirm) {
                    throw new Error("비밀번호 변경란을 모두 입력해주세요.");
                }
                if (form.new_password !== form.new_password_confirm) throw new Error("새 비밀번호 확인이 일치하지 않습니다.");
                if (form.new_password.length < 8) throw new Error("새 비밀번호는 8자 이상이어야 합니다.");
                await authApi.changePassword({
                    current_password: form.current_password,
                    new_password: form.new_password,
                    new_password_confirm: form.new_password_confirm,
                });
            }

            setMsg("저장되었습니다.");
            setEditing(false);
            onUserRefresh?.();
        } catch (e) {
            setMsg(e?.message || "저장 중 오류가 발생했습니다.");
        } finally {
            setSaving(false);
        }
    }

    function onCancel() {
        setForm({
            name: user?.name || "",
            username: user?.username || "",
            email: user?.email || "",
            current_password: "",
            new_password: "",
            new_password_confirm: "",
        });
        setEditing(false);
        setMsg("");
    }

    return (
        <div className="settings-card">
            {/* 카드 헤더: 타이틀 + 우측 액션 */}
            <div className="settings-card__head">
                <h3 className="settings-card__title">내 정보</h3>
                {!editing ? (
                    <button className="btn btn-primary btn-compact" onClick={() => setEditing(true)} disabled={viewing}>
                        <FaEdit /> 편집
                    </button>
                ) : (
                    <div className="row-actions">
                        <button className="btn btn-primary btn-compact" onClick={onSave} disabled={saving}>
                            <FaSave /> {saving ? "저장 중…" : "저장"}
                        </button>
                        <button className="btn btn-compact" onClick={onCancel} disabled={saving}>
                            <FaTimes /> 취소
                        </button>
                    </div>
                )}
            </div>

            {/* 보기 모드: 키-값 리스트 */}
            {!editing && (
                <div className="kv-list">
                    <div className="kv-row">
                        <div className="kv-label">이름</div>
                        <div className="kv-value">{user?.name || "-"}</div>
                    </div>
                    <div className="kv-row">
                        <div className="kv-label">아이디</div>
                        <div className="kv-value mono">@{user?.username || "-"}</div>
                    </div>
                    <div className="kv-row">
                        <div className="kv-label">이메일</div>
                        <div className="kv-value">{user?.email || "-"}</div>
                    </div>
                </div>
            )}

            {/* 편집 모드: 폼 그리드 */}
            {editing && (
                <div className="form-grid nice">
                    <label>이름</label>
                    <input
                        className="admin__input"
                        value={form.name}
                        onChange={(e) => setField("name", e.target.value)}
                        placeholder="이름"
                    />

                    <label>아이디</label>
                    <input
                        className="admin__input"
                        value={form.username}
                        onChange={(e) => setField("username", e.target.value)}
                        placeholder="아이디(로그인 ID)"
                    />

                    <label>이메일</label>
                    <input
                        className="admin__input"
                        value={form.email}
                        onChange={(e) => setField("email", e.target.value)}
                        placeholder="email@example.com"
                    />

                    <div className="form-sep">비밀번호 변경</div>
                    <div className="pwd-grid">
                        <input
                            className="admin__input"
                            type="password"
                            placeholder="현재 비밀번호"
                            value={form.current_password}
                            onChange={(e) => setField("current_password", e.target.value)}
                        />
                        <input
                            className="admin__input"
                            type="password"
                            placeholder="새 비밀번호(8자 이상)"
                            value={form.new_password}
                            onChange={(e) => setField("new_password", e.target.value)}
                        />
                        <input
                            className="admin__input"
                            type="password"
                            placeholder="새 비밀번호 확인"
                            value={form.new_password_confirm}
                            onChange={(e) => setField("new_password_confirm", e.target.value)}
                        />
                    </div>
                </div>
            )}

            {msg && <div className="form-msg ok">{msg}</div>}
        </div>
    );
}
