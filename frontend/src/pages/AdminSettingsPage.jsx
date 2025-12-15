// src/pages/AdminSettingsPage.jsx
// 관리자 설정 페이지 (문서 관리 / 유저 관리)
// - 문서 관리: 문서명/업로더 필터, 업로드 날짜(폴백 포함), 청크 확인, 삭제
// - 유저 관리: 다중 필터, 인라인 편집(아이디/이름/이메일/보안등급/비밀번호), 삭제

import React, { useEffect, useMemo, useState } from "react";

import { adminApi } from "../api/http";
import { fmtDate } from "../utils/dateFormat";

import MarkdownRenderer from "../components/MarkdownRenderer";

import "./AdminSettingsPage.css";

/* =========================================================
   공통: 상단 모드 스위처 (문서 관리 / 유저 관리 / 팀 관리)
   ========================================================= */
function ModeSwitcher({ value, onChange }) {
    const cards = [
        { key: "docs", title: "문서 관리", desc: "벡터 스토어 내 전체 문서 조회/삭제" },
        { key: "users", title: "유저 관리", desc: "유저 조회/삭제/수정(아이디·비번·보안등급)" },
        { key: "teams", title: "팀 관리", desc: "팀 추가/수정/삭제 (문서 격리)" },
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

/* =========================================================
   청크 뷰어 모달
   - 문서의 청크들을 순서대로 확인
   - 좌/우 이동, 마크다운 렌더링
   ========================================================= */
function ChunkViewerModal({ docId, docTitle, onClose }) {
    const [chunks, setChunks] = useState([]);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [imageModalSrc, setImageModalSrc] = useState(null); // 이미지 확대 모달

    useEffect(() => {
        async function loadChunks() {
            setLoading(true);
            setError("");
            try {
                const res = await adminApi.docs.chunks(docId);
                setChunks(res?.chunks || []);
            } catch (e) {
                setError(String(e?.message || e));
            } finally {
                setLoading(false);
            }
        }
        loadChunks();
    }, [docId]);

    // 키보드 이벤트 핸들러
    useEffect(() => {
        function handleKeyDown(e) {
            if (e.key === "Escape") onClose();
            else if (e.key === "ArrowLeft") setCurrentIndex((i) => Math.max(0, i - 1));
            else if (e.key === "ArrowRight") setCurrentIndex((i) => Math.min(chunks.length - 1, i + 1));
        }
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [chunks.length, onClose]);

    const currentChunk = chunks[currentIndex] || null;

    return (
        <div className="chunk-modal__overlay" onClick={onClose}>
            <div className="chunk-modal" onClick={(e) => e.stopPropagation()}>
                {/* 헤더 */}
                <div className="chunk-modal__header">
                    <div className="chunk-modal__title">
                        <span className="chunk-modal__doc-title">{docTitle || docId}</span>
                        <span className="chunk-modal__subtitle">청크 확인</span>
                    </div>
                    <button className="chunk-modal__close" onClick={onClose}>×</button>
                </div>

                {/* 콘텐츠 */}
                <div className="chunk-modal__body">
                    {loading ? (
                        <div className="chunk-modal__loading">청크를 불러오는 중...</div>
                    ) : error ? (
                        <div className="chunk-modal__error">{error}</div>
                    ) : chunks.length === 0 ? (
                        <div className="chunk-modal__empty">청크가 없습니다.</div>
                    ) : (
                        <>
                            {/* 청크 메타 정보 */}
                            <div className="chunk-modal__meta">
                                <span className="chunk-modal__index">
                                    청크 {currentIndex + 1} / {chunks.length}
                                </span>
                                {currentChunk?.page_start && (
                                    <span className="chunk-modal__page">
                                        페이지 {currentChunk.page_start}
                                        {currentChunk.page_end && currentChunk.page_end !== currentChunk.page_start
                                            ? `~${currentChunk.page_end}`
                                            : ""}
                                    </span>
                                )}
                                {currentChunk?.has_image && (
                                    <span className={`chunk-modal__tag chunk-modal__tag--${currentChunk.image_type || "image"}`}>
                                        {currentChunk.image_type === "table" ? "📊 표" : "🖼️ 그림"}
                                    </span>
                                )}
                            </div>

                            {/* 청크 내용 */}
                            <div className="chunk-modal__content">
                                <MarkdownRenderer content={currentChunk?.content || ""} />
                            </div>

                            {/* 이미지 미리보기 (이미지가 있는 경우만) */}
                            {currentChunk?.has_image && currentChunk?.image_url && (
                                <div className="chunk-modal__image-section">
                                    <div className="chunk-modal__image-label">
                                        {currentChunk.image_type === "table" ? "📊 원본 표 이미지" : "🖼️ 원본 그림"}
                                    </div>
                                    <div
                                        className="chunk-modal__image-wrapper"
                                        onClick={() => setImageModalSrc(currentChunk.image_url)}
                                    >
                                        <img
                                            src={currentChunk.image_url}
                                            alt={currentChunk.image_type === "table" ? "표" : "그림"}
                                            className="chunk-modal__image-thumb"
                                        />
                                        <div className="chunk-modal__image-hint">클릭하여 확대</div>
                                    </div>
                                </div>
                            )}

                            {/* 네비게이션 */}
                            <div className="chunk-modal__nav">
                                <button
                                    className="chunk-modal__nav-btn"
                                    onClick={() => setCurrentIndex((i) => Math.max(0, i - 1))}
                                    disabled={currentIndex === 0}
                                >
                                    ← 이전
                                </button>
                                <div className="chunk-modal__nav-dots">
                                    {chunks.length <= 20 ? (
                                        chunks.map((_, idx) => (
                                            <button
                                                key={idx}
                                                className={`chunk-modal__dot ${idx === currentIndex ? "is-active" : ""}`}
                                                onClick={() => setCurrentIndex(idx)}
                                                title={`청크 ${idx + 1}`}
                                            />
                                        ))
                                    ) : (
                                        <span className="chunk-modal__nav-info">
                                            {currentIndex + 1} / {chunks.length}
                                        </span>
                                    )}
                                </div>
                                <button
                                    className="chunk-modal__nav-btn"
                                    onClick={() => setCurrentIndex((i) => Math.min(chunks.length - 1, i + 1))}
                                    disabled={currentIndex === chunks.length - 1}
                                >
                                    다음 →
                                </button>
                            </div>
                        </>
                    )}
                </div>

                {/* 이미지 확대 모달 */}
                {imageModalSrc && (
                    <div
                        className="chunk-image-modal__overlay"
                        onClick={() => setImageModalSrc(null)}
                    >
                        <div className="chunk-image-modal__content" onClick={(e) => e.stopPropagation()}>
                            <button
                                className="chunk-image-modal__close"
                                onClick={() => setImageModalSrc(null)}
                            >
                                ×
                            </button>
                            <img
                                src={imageModalSrc}
                                alt="원본 이미지"
                                className="chunk-image-modal__img"
                            />
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

/* =========================================================
   문서 관리 섹션
   - 문서명/업로더 필터
   - 업로더: 윗줄 = 이름(없으면 아이디), 아랫줄 = @아이디
   - 업로드 날짜: uploaded_at → created_at → updated_at 폴백
   - 청크 확인 버튼 (가시성 대체)
   - 삭제(확인 후 즉시 목록 갱신)
   ========================================================= */
function DocsView() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");

    // 청크 뷰어 모달 상태
    const [chunkViewerDoc, setChunkViewerDoc] = useState(null); // { doc_id, doc_title }

    // 필터 상태
    const [qTitle, setQTitle] = useState("");
    const [qUploader, setQUploader] = useState("");

    // 목록 로드
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
    useEffect(() => { load(); }, []);

    // 필터 적용
    const filtered = useMemo(() => {
        const t = (qTitle || "").trim().toLowerCase();
        const u = (qUploader || "").trim().toLowerCase();
        return (items || []).filter((it) => {
            const title = (it.doc_title || it.doc_id || "").toLowerCase();
            const uploader = `${(it.owner_name || it.owner_username || "").toLowerCase()} ${(it.owner_username || "").toLowerCase()}`;
            return (!t || title.includes(t)) && (!u || uploader.includes(u));
        });
    }, [items, qTitle, qUploader]);

    // 삭제
    async function handleDelete(doc_id) {
        if (!window.confirm(`[${doc_id}] 문서를 삭제할까요? 연관된 모든 청크/파일이 제거됩니다.`)) return;
        try {
            await adminApi.docs.remove(doc_id);
            // 낙관적 반영: 재로딩 없이 목록에서 제거
            setItems((prev) => prev.filter((it) => it.doc_id !== doc_id));
        } catch (e) {
            alert(`삭제 실패: ${e?.message || e}`);
        }
    }

    return (
        <div className="admin__panel">
            <div className="admin__panel_head">
                <div className="admin__panel_ttl">문서 관리</div>
                <div className="admin__panel_desc">전체 문서를 조회/검색하고 삭제할 수 있습니다.</div>
            </div>

            {/* 유저 관리와 동일한 2열 필터 레이아웃 */}
            <div className="admin__filters admin__filters--docs admin__filters--compact">
                <div className="admin__filter">
                    <label className="admin__filter_lbl">문서명</label>
                    <input
                        className="admin__input admin__input--narrow"
                        placeholder="문서명 검색"
                        value={qTitle}
                        onChange={(e) => setQTitle(e.target.value)}
                    />
                </div>
                <div className="admin__filter">
                    <label className="admin__filter_lbl">업로더</label>
                    <input
                        className="admin__input admin__input--narrow"
                        placeholder="이름/아이디 검색"
                        value={qUploader}
                        onChange={(e) => setQUploader(e.target.value)}
                    />
                </div>
            </div>

            {err && <div className="admin__banner error">{err}</div>}

            {loading ? (
                <div className="admin__empty">불러오는 중…</div>
            ) : filtered.length === 0 ? (
                <div className="admin__empty">표시할 문서가 없습니다.</div>
            ) : (
                <div className="admin__tablewrap">
                    <table className="admin__table">
                        <thead>
                            <tr>
                                <th className="col-index">#</th>
                                <th>문서명</th>
                                <th className="col-uploader">업로더</th>
                                <th className="col-date">업로드 날짜</th>
                                <th className="col-team">팀</th>
                                <th className="col-chunks">청크수</th>
                                <th className="col-chunk-view">청크 확인</th>
                                <th className="col-preview">미리보기</th>
                                <th className="col-actions">삭제</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((it, idx) => (
                                <tr key={it.doc_id}>
                                    <td className="col-index">{idx + 1}</td>
                                    <td title={it.doc_title || it.doc_id}>
                                        <div className="admin__title">{it.doc_title || it.doc_id}</div>
                                    </td>
                                    <td className="col-uploader" title={it.owner_username || "-"}>
                                        @{it.owner_username || "-"}
                                    </td>
                                    {/* 백엔드에서 uploaded_at이 없을 수 있으므로 폴백 적용 */}
                                    <td className="admin__muted col-date">
                                        {fmtDate(it.uploaded_at || it.created_at || it.updated_at)}
                                    </td>
                                    <td className="col-team">{it.team_name || "-"}</td>
                                    <td className="col-chunks">{it.chunk_count ?? 0}</td>
                                    <td className="col-chunk-view">
                                        <button
                                            className="btn btn-chunk-view"
                                            onClick={() => setChunkViewerDoc({
                                                doc_id: it.doc_id,
                                                doc_title: it.doc_title || it.doc_id
                                            })}
                                        >
                                            확인
                                        </button>
                                    </td>
                                    <td className="col-preview">
                                        {it.doc_url ? (
                                            <a href={it.doc_url} target="_blank" rel="noreferrer">열기</a>
                                        ) : (
                                            <span className="admin__sub">URL 없음</span>
                                        )}
                                    </td>
                                    <td className="col-actions">
                                        <div className="admin__actions">
                                            <button className="btn btn-danger" onClick={() => handleDelete(it.doc_id)}>
                                                삭제
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* 청크 뷰어 모달 */}
            {chunkViewerDoc && (
                <ChunkViewerModal
                    docId={chunkViewerDoc.doc_id}
                    docTitle={chunkViewerDoc.doc_title}
                    onClose={() => setChunkViewerDoc(null)}
                />
            )}
        </div>
    );
}

/* =========================================================
   팀 관리 섹션
   - 팀 추가/수정/삭제
   - 팀 이름, 설명, 활성화 상태 관리
   ========================================================= */
function TeamsView() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");

    // 편집 상태
    const [editingId, setEditingId] = useState(null);
    const [form, setForm] = useState({ name: "", description: "", is_active: true });

    // 새 팀 추가 모드
    const [isAdding, setIsAdding] = useState(false);
    const [newForm, setNewForm] = useState({ name: "", description: "" });

    // 목록 로드
    async function load() {
        setLoading(true);
        setErr("");
        try {
            const res = await adminApi.teams.list();
            setItems(res || []);
        } catch (e) {
            setErr(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    }
    useEffect(() => { load(); }, []);

    // 새 팀 추가
    async function handleCreate() {
        if (!newForm.name.trim()) {
            alert("팀 이름을 입력하세요.");
            return;
        }
        try {
            await adminApi.teams.create({
                name: newForm.name.trim(),
                description: newForm.description.trim() || null,
            });
            setNewForm({ name: "", description: "" });
            setIsAdding(false);
            await load();
        } catch (e) {
            alert("팀 추가 실패: " + (e?.message || e));
        }
    }

    // 편집 시작/취소
    function startEdit(team) {
        setEditingId(team.id);
        setForm({
            name: team.name || "",
            description: team.description || "",
            is_active: team.is_active !== false,
        });
    }
    function cancelEdit() {
        setEditingId(null);
        setForm({ name: "", description: "", is_active: true });
    }

    // 저장
    async function saveEdit(id) {
        const cur = items.find((x) => x.id === id) || {};
        const payload = {};
        if (form.name && form.name !== (cur.name || "")) payload.name = form.name;
        if (form.description !== (cur.description || "")) payload.description = form.description || null;
        if (form.is_active !== cur.is_active) payload.is_active = form.is_active;

        if (Object.keys(payload).length === 0) {
            alert("변경 사항이 없습니다.");
            return;
        }

        try {
            await adminApi.teams.update(id, payload);
            await load();
            cancelEdit();
        } catch (e) {
            alert("저장 실패: " + (e?.message || e));
        }
    }

    // 삭제
    async function removeTeam(id, name) {
        if (!window.confirm(`[${name}] 팀을 삭제할까요?\n소속 유저들은 '미배정' 상태가 됩니다.`)) return;
        try {
            await adminApi.teams.remove(id);
            await load();
        } catch (e) {
            alert("삭제 실패: " + (e?.message || e));
        }
    }

    return (
        <div className="admin__panel">
            <div className="admin__panel_head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                    <div className="admin__panel_ttl">팀 관리</div>
                    <div className="admin__panel_desc">팀을 추가/수정/삭제합니다. 각 팀은 독립적인 문서 저장소를 가집니다.</div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn-primary" onClick={() => setIsAdding(true)} disabled={isAdding}>
                        + 팀 추가
                    </button>
                    <button className="btn" onClick={load} disabled={loading}>새로고침</button>
                </div>
            </div>

            {err && <div className="admin__banner error">{err}</div>}

            {/* 새 팀 추가 폼 */}
            {isAdding && (
                <div className="admin__add-form">
                    <div className="admin__add-form-row">
                        <input
                            className="admin__input"
                            placeholder="팀 이름 (필수)"
                            value={newForm.name}
                            onChange={(e) => setNewForm((f) => ({ ...f, name: e.target.value }))}
                            autoFocus
                        />
                        <input
                            className="admin__input"
                            placeholder="설명 (선택)"
                            value={newForm.description}
                            onChange={(e) => setNewForm((f) => ({ ...f, description: e.target.value }))}
                            style={{ flex: 2 }}
                        />
                        <button className="btn btn-primary" onClick={handleCreate}>추가</button>
                        <button className="btn" onClick={() => { setIsAdding(false); setNewForm({ name: "", description: "" }); }}>취소</button>
                    </div>
                </div>
            )}

            {loading ? (
                <div className="admin__empty">불러오는 중…</div>
            ) : items.length === 0 ? (
                <div className="admin__empty">등록된 팀이 없습니다. 위의 '팀 추가' 버튼을 눌러 팀을 추가하세요.</div>
            ) : (
                <div className="admin__tablewrap">
                    <table className="admin__table">
                        <thead>
                            <tr>
                                <th className="col-index">#</th>
                                <th>팀 이름</th>
                                <th>설명</th>
                                <th className="col-status">상태</th>
                                <th className="col-actions">동작</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((team, idx) => {
                                const editing = editingId === team.id;
                                return (
                                    <tr key={team.id}>
                                        <td className="col-index">{idx + 1}</td>
                                        <td>
                                            {editing ? (
                                                <input
                                                    className="admin__input"
                                                    value={form.name}
                                                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                                                    placeholder="팀 이름"
                                                />
                                            ) : (
                                                <>
                                                    <div className="admin__title">{team.name}</div>
                                                    <div className="admin__sub">ID: {team.id}</div>
                                                </>
                                            )}
                                        </td>
                                        <td>
                                            {editing ? (
                                                <input
                                                    className="admin__input"
                                                    value={form.description}
                                                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                                                    placeholder="설명"
                                                />
                                            ) : (
                                                team.description || <span className="admin__sub">-</span>
                                            )}
                                        </td>
                                        <td className="col-status">
                                            {editing ? (
                                                <select
                                                    className="admin__select"
                                                    value={form.is_active ? "active" : "inactive"}
                                                    onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.value === "active" }))}
                                                >
                                                    <option value="active">활성</option>
                                                    <option value="inactive">비활성</option>
                                                </select>
                                            ) : (
                                                <span className={`admin__badge ${team.is_active !== false ? "badge-active" : "badge-inactive"}`}>
                                                    {team.is_active !== false ? "활성" : "비활성"}
                                                </span>
                                            )}
                                        </td>
                                        <td className="col-actions">
                                            <div className="admin__actions">
                                                {editing ? (
                                                    <>
                                                        <button className="btn btn-primary" onClick={() => saveEdit(team.id)}>저장</button>
                                                        <button className="btn" onClick={cancelEdit}>취소</button>
                                                    </>
                                                ) : (
                                                    <>
                                                        <button className="btn" onClick={() => startEdit(team)}>편집</button>
                                                        <button className="btn btn-danger" onClick={() => removeTeam(team.id, team.name)}>삭제</button>
                                                    </>
                                                )}
                                            </div>
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

/* =========================================================
   유저 관리 섹션
   - 다중 필터(인덱스/아이디/이름/이메일/보안등급)
   - 인라인 편집/저장/취소, 삭제
   - 불필요한 툴바/상태표시는 유지해도 무방하지만
     복잡도를 줄이기 위해 "새로고침" 버튼만 남김
   ========================================================= */
function UsersView() {
    const [items, setItems] = useState([]);
    const [teams, setTeams] = useState([]);  // 팀 목록
    const [editingId, setEditingId] = useState(null);
    const [form, setForm] = useState({
        username: "", name: "", email: "", password: "", security_level: 3, team_id: null,
    });
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");

    // 필터 상태
    const [fqId, setFqId] = useState("");
    const [fqUsername, setFqUsername] = useState("");
    const [fqName, setFqName] = useState("");
    const [fqEmail, setFqEmail] = useState("");
    const [fqLevel, setFqLevel] = useState("");
    const [fqTeam, setFqTeam] = useState("");  // 팀 필터

    // 목록 로드 (유저 + 팀)
    async function load() {
        setLoading(true);
        setErr("");
        try {
            const [usersRes, teamsRes] = await Promise.all([
                adminApi.users.list(),
                adminApi.teams.list(),
            ]);
            setItems(usersRes || []);
            setTeams(teamsRes || []);
        } catch (e) {
            setErr(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    }
    useEffect(() => { load(); }, []);

    // 편집 시작/취소
    function startEdit(u) {
        setEditingId(u.id);
        setForm({
            username: u.username || "",
            name: u.name || "",
            email: u.email || "",
            password: "",
            security_level: Number(u.security_level ?? 3),
            team_id: u.team_id ?? null,
        });
    }
    function cancelEdit() {
        setEditingId(null);
        setForm({ username: "", name: "", email: "", password: "", security_level: 3, team_id: null });
    }

    // 저장
    async function saveEdit(id) {
        const cur = items.find((x) => x.id === id) || {};
        const payload = {};
        if (form.username && form.username !== (cur.username || "")) payload.username = form.username;
        if (form.name && form.name !== (cur.name || "")) payload.name = form.name;
        if (form.email && form.email !== (cur.email || "")) payload.email = form.email;
        if (form.password && form.password.length >= 8) payload.password = form.password;
        if (Number.isFinite(Number(form.security_level))) payload.security_level = Number(form.security_level);
        // 팀 변경 (null 허용)
        if (form.team_id !== cur.team_id) payload.team_id = form.team_id;
        if (Object.keys(payload).length === 0) { alert("변경 사항이 없습니다."); return; }

        try {
            await adminApi.users.update(id, payload);
            await load();
            cancelEdit();
            // 유저 정보 변경 시 다른 페이지에 알림 (업로드 페이지 등)
            window.dispatchEvent(new CustomEvent("auth:changed"));
            alert("저장 완료");
        } catch (e) {
            alert("저장 실패: " + (e?.message || e));
        }
    }

    // 삭제
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

    // 필터 적용
    const filtered = useMemo(() => {
        const qId = (fqId || "").trim().toLowerCase();
        const qU = (fqUsername || "").trim().toLowerCase();
        const qN = (fqName || "").trim().toLowerCase();
        const qE = (fqEmail || "").trim().toLowerCase();
        const qL = (fqLevel || "").trim().toLowerCase();
        const qT = fqTeam;  // 팀 필터 (ID 문자열 또는 빈 문자열)
        return (items || []).filter((u) => {
            const idStr = String(u.id || "").toLowerCase();
            const un = (u.username || "").toLowerCase();
            const nm = (u.name || "").toLowerCase();
            const em = (u.email || "").toLowerCase();
            const lv = String(u.security_level ?? "").toLowerCase();
            const teamMatch = !qT || (qT === "null" ? u.team_id === null : String(u.team_id) === qT);
            return (!qId || idStr.includes(qId))
                && (!qU || un.includes(qU))
                && (!qN || nm.includes(qN))
                && (!qE || em.includes(qE))
                && (!qL || lv === qL)
                && teamMatch;
        });
    }, [items, fqId, fqUsername, fqName, fqEmail, fqLevel, fqTeam]);

    return (
        <div className="admin__panel">
            {/* 간단한 툴바: 새로고침만 유지 (필요 시 확장 가능) */}
            <div className="admin__panel_head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                    <div className="admin__panel_ttl">유저 관리</div>
                    <div className="admin__panel_desc">유저 조회/수정/삭제 및 필터링</div>
                </div>
                <button className="btn btn-primary" onClick={load} disabled={loading}>새로고침</button>
            </div>
            {err && <div className="admin__banner error">{err}</div>}

            {/* 필터 그리드 */}
            <div className="admin__filters admin__filters--users admin__filters--compact">
                <div className="admin__filter">
                    <label className="admin__filter_lbl">인덱스(ID)</label>
                    <input className="admin__input admin__input--narrow" value={fqId} onChange={(e) => setFqId(e.target.value)} placeholder="예: 12" />
                </div>
                <div className="admin__filter">
                    <label className="admin__filter_lbl">아이디</label>
                    <input className="admin__input admin__input--narrow" value={fqUsername} onChange={(e) => setFqUsername(e.target.value)} placeholder="아이디 검색" />
                </div>
                <div className="admin__filter">
                    <label className="admin__filter_lbl">이름</label>
                    <input className="admin__input admin__input--narrow" value={fqName} onChange={(e) => setFqName(e.target.value)} placeholder="이름 검색" />
                </div>
                <div className="admin__filter">
                    <label className="admin__filter_lbl">이메일</label>
                    <input className="admin__input admin__input--narrow" value={fqEmail} onChange={(e) => setFqEmail(e.target.value)} placeholder="이메일 검색" />
                </div>
                <div className="admin__filter">
                    <label className="admin__filter_lbl">보안등급</label>
                    <select className="admin__select admin__input--narrow" value={fqLevel} onChange={(e) => setFqLevel(e.target.value)}>
                        <option value="">전체</option>
                        {[1, 2, 3, 4].map((l) => <option key={l} value={String(l)}>{l}</option>)}
                    </select>
                </div>
                <div className="admin__filter">
                    <label className="admin__filter_lbl">소속팀</label>
                    <select className="admin__select admin__input--narrow" value={fqTeam} onChange={(e) => setFqTeam(e.target.value)}>
                        <option value="">전체</option>
                        <option value="null">미배정</option>
                        {teams.map((t) => <option key={t.id} value={String(t.id)}>{t.name}</option>)}
                    </select>
                </div>
            </div>

            {filtered.length === 0 ? (
                <div className="admin__empty">조건에 맞는 사용자가 없습니다.</div>
            ) : (
                <div className="admin__tablewrap">
                    <table className="admin__table">
                        <thead>
                            <tr>
                                <th className="col-index">인덱스</th>
                                <th>아이디</th>
                                <th>이름</th>
                                <th>이메일</th>
                                <th className="col-team">소속팀</th>
                                <th className="col-level">보안등급</th>
                                <th style={{ width: 200 }}>비밀번호 변경</th>
                                <th className="col-actions">동작</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((u, idx) => {
                                const editing = editingId === u.id;
                                return (
                                    <tr key={u.id}>
                                        <td className="col-index">{idx + 1}</td>
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
                                                <input
                                                    className="admin__input"
                                                    value={form.name}
                                                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                                                    placeholder="이름"
                                                />
                                            ) : (u.name || "-")}
                                        </td>
                                        <td>
                                            {editing ? (
                                                <input
                                                    className="admin__input"
                                                    value={form.email}
                                                    onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                                                    placeholder="이메일"
                                                />
                                            ) : (u.email || "-")}
                                        </td>
                                        <td className="col-team">
                                            {editing ? (
                                                <select
                                                    className="admin__select"
                                                    value={form.team_id ?? ""}
                                                    onChange={(e) => setForm((f) => ({
                                                        ...f,
                                                        team_id: e.target.value === "" ? null : Number(e.target.value)
                                                    }))}
                                                >
                                                    <option value="">미배정</option>
                                                    {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                                                </select>
                                            ) : (u.team_name || <span className="admin__sub">미배정</span>)}
                                        </td>
                                        <td className="col-level">
                                            {editing ? (
                                                <select
                                                    className="admin__select"
                                                    value={form.security_level}
                                                    onChange={(e) => setForm((f) => ({ ...f, security_level: Number(e.target.value) }))}
                                                >
                                                    {[1, 2, 3, 4].map((l) => <option key={l} value={l}>{l}</option>)}
                                                </select>
                                            ) : (u.security_level ?? "-")}
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
                                            ) : (<span className="admin__sub">편집을 눌러 변경</span>)}
                                        </td>
                                        <td className="col-actions">
                                            <div className="admin__actions">
                                                {editing ? (
                                                    <>
                                                        <button className="btn btn-primary" onClick={() => saveEdit(u.id)}>저장</button>
                                                        <button className="btn" onClick={cancelEdit}>취소</button>
                                                    </>
                                                ) : (
                                                    <>
                                                        <button className="btn" onClick={() => startEdit(u)}>편집</button>
                                                        <button className="btn btn-danger" onClick={() => removeUser(u.id)}>삭제</button>
                                                    </>
                                                )}
                                            </div>
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

/* =========================================================
   루트: 관리자 설정
   ========================================================= */
export default function AdminSettingsPage() {
    const [mode, setMode] = useState("docs"); // 기본 탭: 문서 관리

    // 현재 모드에 따른 뷰 렌더링
    function renderView() {
        switch (mode) {
            case "docs":
                return <DocsView />;
            case "users":
                return <UsersView />;
            case "teams":
                return <TeamsView />;
            default:
                return <DocsView />;
        }
    }

    return (
        <div className="admin">
            <div className="admin__header">
                <h1>관리자 설정</h1>
                <div className="admin__desc">1등급 관리자 전용 페이지</div>
            </div>
            <ModeSwitcher value={mode} onChange={setMode} />
            {renderView()}
        </div>
    );
}
