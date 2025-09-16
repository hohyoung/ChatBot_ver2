import React, { useEffect, useState } from "react";
import "./SettingPage.css"; // ✅ CSS 분리
import { docsApi } from "../api/http";

export default function SettingsPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

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

  useEffect(() => {
    load();
  }, []);

  async function onDelete(doc_id) {
    if (!confirm("이 문서를 삭제할까요? (연관 청크/피드백도 삭제됩니다)")) return;
    try {
      await docsApi.deleteMy(doc_id);
      await load();
    } catch (e) {
      alert(e?.message || "삭제 실패");
    }
  }

  const visibilityChip = (v) => {
    const vv = (v || "").toLowerCase();
    const cls =
      vv === "public" ? "chip chip--public" :
      vv === "private" ? "chip chip--private" :
      "chip chip--org";
    const label =
      vv === "public" ? "공개" :
      vv === "private" ? "비공개" :
      "사내";
    return <span className={cls}>{label}</span>;
  };

  return (
    <div className="settings-page">
      <h2 className="page-title">설정</h2>
      <p className="page-subtitle">내가 업로드한 문서들을 확인하고 관리할 수 있습니다.</p>

      {err && <div className="banner error">{err}</div>}

      <div className="section">
        <div className="toolbar">
          <span className="small">총 {items.length}건</span>
        </div>

        <div className="card table-card">
          {loading ? (
            <div className="empty">불러오는 중…</div>
          ) : items.length === 0 ? (
            <div className="empty">업로드한 문서가 없습니다.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>제목</th>
                  <th>doc_id</th>
                  <th>가시성</th>
                  <th>청크수</th>
                  <th>미리보기</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.doc_id}>
                    <td>{it.doc_title || "-"}</td>
                    <td className="mono">{it.doc_id}</td>
                    <td>{visibilityChip(it.visibility)}</td>
                    <td>{it.chunk_count}</td>
                    <td>
                      {it.doc_url ? (
                        <a href={it.doc_url} target="_blank" rel="noreferrer">
                          열기
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <button
                        className="btn btn-danger"
                        onClick={() => onDelete(it.doc_id)}
                        aria-label={`문서 삭제: ${it.doc_title || it.doc_id}`}
                      >
                        삭제
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
