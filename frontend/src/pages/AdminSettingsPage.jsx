import React, { useEffect, useMemo, useState } from "react";
import "./AdminSettingsPage.css";
import { adminApi } from "../api/http"; // http.js 하단에 추가한 adminApi 사용

// 상단 카드 선택형 스위처
function ModeSwitcher({ value, onChange }) {
    const cards = [
        { key: "docs", title: "문서 관리", desc: "벡터 스토어 내 전체 문서 조회/삭제" },
        { key: "users", title: "유저 관리", desc: "유저 조회/삭제/수정(아이디·비번·보안등급)" },
    ];
    return (
        <div className="admin__switcher">
            {cards.map((c) => (
                <button
                    key={c.key}
                    onClick={() => onChange(c.key)}
                    className={"admin__card" + (value === c.key ? " is-active" : "")}
                >
                    <div className="admin__card_ttl">{c.title}</div>
                    <div className="admin__card_desc">{c.desc}</div>
                </button>
            ))}
        </div>
    );
}

/* ------------------- 문서 관리 뷰 ------------------- */
function DocsView() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");

    async function load() {
        setLoading(true);
        setErr("");
        try {
            const res = await adminApi.docs.list();
            setItems(res?.items || []);
        } catch (e) {
            setErr(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    }

    async function handleDelete(doc_id) {
        if (!window.confirm("정말 삭제할까요? 이 문서의 모든 청크와 파일이 삭제됩니다.")) return;
        try {
            await adminApi.docs.remove(doc_id);
            await load();
            alert("삭제 완료");
        } catch (e) {
            alert("삭제 실패: " + (e?.message || e));
        }
    }

    useEffect(() => { load(); }, []);

    return (
        <div className="admin__panel">
            <div className="admin__toolbar">
                <div className="admin__toolbar_l">
                    <button className="btn btn-primary" onClick={load} disabled={loading}>새로고침</button>
                </div>
                <div className="admin__toolbar_r">
                    {loading && <span className="admin__hint">불러오는 중…</span>}
                    {err && <span className="admin__err">{err}</span>}
                </div>
            </div>

            {items.length === 0 ? (
                <div className="admin__empty">표시할 문서가 없습니다.</div>
            ) : (
                <div className="admin__tablewrap">
                    <table className="admin__table">
                        <thead>
                            <tr>
                                <th style={{ width: 56 }}>#</th>
                                <th>문서명</th>
                                <th>업로더</th>
                                <th>가시성</th>
                                <th style={{ width: 96 }}>청크수</th>
                                <th style={{ width: 120 }}>미리보기</th>
                                <th style={{ width: 80 }}>삭제</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((it, idx) => (
                                <tr key={it.doc_id}>
                                    <td>{idx + 1}</td>
                                    <td title={it.doc_id}>
                                        <div className="admin__title">{it.doc_title || it.doc_id}</div>
                                        <div className="admin__sub">doc_id: {it.doc_id}</div>
                                    </td>
                                    <td>
                                        <div>{it.owner_username || "-"}</div>
                                        <div className="admin__sub">#{it.owner_id ?? "-"}</div>
                                    </td>
                                    <td>{it.visibility || "-"}</td>
                                    <td style={{ textAlign: "right" }}>{it.chunk_count ?? 0}</td>
                                    <td>
                                        {it.doc_url ? (
                                            <a href={it.doc_url} target="_blank" rel="noreferrer">열기</a>
                                        ) : (
                                            <span className="admin__sub">URL 없음</span>
                                        )}
                                    </td>
                                    <td>
                                        <button className="btn" onClick={() => handleDelete(it.doc_id)}>삭제</button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

/* ------------------- 유저 관리 뷰 ------------------- */
function UsersView() {
    const [items, setItems] = useState([]);
    const [editingId, setEditingId] = useState(null);
    const [form, setForm] = useState({ username: "", password: "", security_level: 3 });
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");

    async function load() {
        setLoading(true);
        setErr("");
        try {
            const list = await adminApi.users.list();
            setItems(list || []);
        } catch (e) {
            setErr(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    }

    function startEdit(u) {
        setEditingId(u.id);
        setForm({
            username: u.username || "",
            password: "",
            security_level: Number(u.security_level ?? 3),
        });
    }
    function cancelEdit() {
        setEditingId(null);
        setForm({ username: "", password: "", security_level: 3 });
    }

    async function saveEdit(id) {
        const payload = {};
        if (form.username && form.username !== (items.find(x => x.id === id)?.username || "")) {
            payload.username = form.username;
        }
        if (form.password && form.password.length >= 8) {
            payload.password = form.password;
        }
        if (Number.isFinite(Number(form.security_level))) {
            payload.security_level = Number(form.security_level);
        }
        if (Object.keys(payload).length === 0) {
            alert("변경 사항이 없습니다.");
            return;
        }
        try {
            await adminApi.users.update(id, payload);
            await load();
            cancelEdit();
            alert("저장 완료");
        } catch (e) {
            alert("저장 실패: " + (e?.message || e));
        }
    }

    async function removeUser(id) {
        if (!window.confirm("이 사용자를 삭제할까요?")) return;
        try {
            await adminApi.users.remove(id);
            await load();
            alert("삭제 완료");
        } catch (e) {
            alert("삭제 실패: " + (e?.message || e));
        }
    }

    useEffect(() => { load(); }, []);

    return (
        <div className="admin__panel">
            <div className="admin__toolbar">
                <div className="admin__toolbar_l">
                    <button className="btn btn-primary" onClick={load} disabled={loading}>새로고침</button>
                </div>
                <div className="admin__toolbar_r">
                    {loading && <span className="admin__hint">불러오는 중…</span>}
                    {err && <span className="admin__err">{err}</span>}
                </div>
            </div>

            {items.length === 0 ? (
                <div className="admin__empty">표시할 사용자가 없습니다.</div>
            ) : (
                <div className="admin__tablewrap">
                    <table className="admin__table">
                        <thead>
                            <tr>
                                <th style={{ width: 56 }}>#</th>
                                <th>아이디</th>
                                <th style={{ width: 120 }}>보안등급</th>
                                <th style={{ width: 240 }}>비밀번호 변경</th>
                                <th style={{ width: 160 }}>동작</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((u, idx) => {
                                const editing = editingId === u.id;
                                return (
                                    <tr key={u.id}>
                                        <td>{idx + 1}</td>
                                        <td>
                                            {editing ? (
                                                <input
                                                    className="admin__input"
                                                    value={form.username}
                                                    onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                                                    placeholder="아이디"
                                                />
                                            ) : (
                                                <>
                                                    <div className="admin__title">{u.username}</div>
                                                    <div className="admin__sub">#{u.id}</div>
                                                </>
                                            )}
                                        </td>
                                        <td>
                                            {editing ? (
                                                <select
                                                    className="admin__select"
                                                    value={form.security_level}
                                                    onChange={(e) => setForm((f) => ({ ...f, security_level: Number(e.target.value) }))}
                                                >
                                                    {[1, 2, 3, 4].map(l => <option key={l} value={l}>{l}</option>)}
                                                </select>
                                            ) : (
                                                <span>{u.security_level ?? "-"}</span>
                                            )}
                                        </td>
                                        <td>
                                            {editing ? (
                                                <input
                                                    className="admin__input"
                                                    type="password"
                                                    placeholder="새 비밀번호(8자 이상)"
                                                    value={form.password}
                                                    onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                                                />
                                            ) : (
                                                <span className="admin__sub">편집을 눌러 변경</span>
                                            )}
                                        </td>
                                        <td>
                                            {editing ? (
                                                <>
                                                    <button className="btn btn-primary" onClick={() => saveEdit(u.id)}>저장</button>
                                                    <button className="btn" onClick={cancelEdit} style={{ marginLeft: 8 }}>취소</button>
                                                </>
                                            ) : (
                                                <>
                                                    <button className="btn" onClick={() => startEdit(u)}>편집</button>
                                                    <button className="btn" onClick={() => removeUser(u.id)} style={{ marginLeft: 8 }}>삭제</button>
                                                </>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

/* ------------------- 페이지 ------------------- */
export default function AdminSettingsPage() {
    const [mode, setMode] = useState("docs"); // "docs" | "users"
    return (
        <div className="admin">
            <div className="admin__header">
                <h1>관리자 설정</h1>
                <div className="admin__desc">1등급 관리자 전용 페이지</div>
            </div>
            <ModeSwitcher value={mode} onChange={setMode} />
            {mode === "docs" ? <DocsView /> : <UsersView />}
        </div>
    );
}
