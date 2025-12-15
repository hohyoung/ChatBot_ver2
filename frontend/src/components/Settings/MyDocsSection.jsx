import React, { useEffect, useMemo, useState } from "react";
import "./Settings.css";
import { fmtDate } from "../../utils/dateFormat";

/** 메타에서 대표 업로드 시각을 Date로 반환 (없으면 null) */
const getItemDate = (it) => {
    const raw = it?.uploaded_at || it?.created_at || it?.updated_at;
    if (!raw) return null;
    const d = new Date(raw);
    return Number.isNaN(d.getTime()) ? null : d;
};

export default function MyDocsSection({ isLoggedIn, docsApi }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");

    // 🔎 필터 상태
    const [qTitle, setQTitle] = useState("");
    const [qFrom, setQFrom] = useState(""); // YYYY-MM-DD
    const [qTo, setQTo] = useState("");     // YYYY-MM-DD

    useEffect(() => {
        if (!isLoggedIn) {
            setItems([]);
            setLoading(false);
            return;
        }
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isLoggedIn]);

    async function load() {
        setLoading(true);
        setErr("");
        try {
            const res = await docsApi.myList();
            setItems(res?.items || []);
        } catch (e) {
            setErr(e?.message || "목록을 불러올 수 없습니다.");
        } finally {
            setLoading(false);
        }
    }

    async function onDelete(doc_id) {
        if (!isLoggedIn) return;
        if (!confirm("이 문서를 삭제할까요? (연관 청크/피드백도 삭제됩니다)")) return;
        try {
            await docsApi.remove(doc_id);
            await load();
        } catch (e) {
            alert(e?.message || "삭제 실패");
        }
    }

    /** 빠른 기간 선택 */
    const setQuickRange = (days) => {
        if (days === "all") { setQFrom(""); setQTo(""); return; }
        const end = new Date();
        const start = new Date();
        start.setDate(end.getDate() - (days - 1));
        const to = end.toISOString().slice(0, 10);
        const from = start.toISOString().slice(0, 10);
        setQFrom(from); setQTo(to);
    };

    /** 필터 적용 목록 */
    const filtered = useMemo(() => {
        const title = (qTitle || "").trim().toLowerCase();
        const from = qFrom ? new Date(`${qFrom}T00:00:00`) : null;
        const to = qTo ? new Date(`${qTo}T23:59:59.999`) : null;

        return (items || []).filter((it) => {
            const name = (it.doc_title || "").toLowerCase();
            if (title && !name.includes(title)) return false;

            const d = getItemDate(it);
            if (from && (!d || d < from)) return false;
            if (to && (!d || d > to)) return false;

            return true;
        });
    }, [items, qTitle, qFrom, qTo]);

    if (err) return <div className="banner error">{err}</div>;
    if (loading) return <div className="empty">불러오는 중…</div>;
    if (!isLoggedIn) return <div className="empty">로그인하면 내 문서 목록이 표시됩니다.</div>;
    if (items.length === 0) return <div className="empty">업로드한 문서가 없습니다.</div>;

    return (
        <div className="settings-card">
            <div className="settings-card__head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <h3 className="settings-card__title" style={{ margin: 0 }}>내 문서</h3>

                {/* 🔎 필터: 제목 + 기간(친절한 UI) */}
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    {/* 제목 검색 */}
                    <input
                        className="admin__input admin__input--narrow"
                        placeholder="제목 검색"
                        value={qTitle}
                        onChange={(e) => setQTitle(e.target.value)}
                        aria-label="제목 검색"
                    />

                    {/* 기간 범위 컨트롤: 라벨 · from ~ to · 지우기 · 빠른선택 */}
                    <div className="range">
                        <span className="range__label">기간</span>
                        <input
                            className="admin__input range__input"
                            type="date"
                            value={qFrom}
                            onChange={(e) => setQFrom(e.target.value)}
                            aria-label="시작일"
                        />
                        <span className="range__sep" aria-hidden>~</span>
                        <input
                            className="admin__input range__input"
                            type="date"
                            value={qTo}
                            onChange={(e) => setQTo(e.target.value)}
                            aria-label="종료일"
                        />
                        <button
                            type="button"
                            className="btn btn--range-clear"
                            onClick={() => { setQFrom(""); setQTo(""); }}
                            title="기간 지우기"
                        >
                            지우기
                        </button>
                    </div>

                    {/* 빠른 선택 */}
                    <div className="quick" style={{ display: "flex", gap: 6 }}>
                        <button type="button" className="btn" onClick={() => setQuickRange(7)}>최근 7일</button>
                        <button type="button" className="btn" onClick={() => setQuickRange(30)}>최근 30일</button>
                        <button type="button" className="btn" onClick={() => setQuickRange("all")}>전체</button>
                    </div>
                </div>
            </div>

            <table className="data-table pretty my-docs-table">
                <thead>
                    <tr>
                        <th className="col-title">제목</th>
                        <th className="col-date">업로드 날짜</th>
                        <th className="col-team">팀</th>
                        <th className="col-num">청크수</th>
                        <th className="col-preview">미리보기</th>
                        <th className="col-delete">삭제</th>
                    </tr>
                </thead>
                <tbody>
                    {filtered.map((it) => (
                        <tr key={it.doc_id}>
                            <td className="col-title">
                                <div className="cell-title">{it.doc_title || "-"}</div>
                            </td>
                            <td className="col-date muted">{fmtDate(it.uploaded_at || it.created_at || it.updated_at)}</td>
                            <td className="col-team">{it.team_name || "-"}</td>
                            <td className="col-num">{it.chunk_count ?? 0}</td>
                            <td className="col-preview">
                                {it.doc_url ? <a href={it.doc_url} target="_blank" rel="noreferrer">열기</a> : "—"}
                            </td>
                            <td className="col-delete">
                                <button className="btn btn-danger btn-sm" onClick={() => onDelete(it.doc_id)}>삭제</button>
                            </td>
                        </tr>
                    ))}
                    {filtered.length === 0 && (
                        <tr>
                            <td colSpan={6} className="muted" style={{ textAlign: "center", padding: "16px" }}>
                                조건에 맞는 문서가 없습니다.
                            </td>
                        </tr>
                    )}
                </tbody>
            </table>
        </div>
    );
}
