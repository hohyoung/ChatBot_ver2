// frontend/src/components/DocViewer/DocViewer.jsx
import React, { useEffect, useMemo, useState } from "react";
import "./DocViewer.css";

function buildDocUrl(meta) {
    if (!meta) return null;

    const relRaw = String(meta.doc_relpath || "");
    const relNorm = relRaw.replace(/\\/g, "/").replace(/^\/+/, ""); // \ → /, 선행 / 제거

    // public/ 또는 static/docs/ 접두어 제거
    let relCore = relNorm;
    for (const p of ["public/", "static/docs/"]) {
        if (relCore.startsWith(p)) relCore = relCore.slice(p.length);
    }

    // 서버가 준 doc_url 우선, 없으면 /static/docs/<core>
    let url = meta.doc_url || (relCore ? `/static/docs/${relCore}` : null);
    if (url) {
        // 과거 데이터 보호: 중복 접두어 정리
        url = url.replace("/static/docs/public/", "/static/docs/");
        url = url.replace("/static/docs/static/docs/", "/static/docs/");
    }

    const page = Number(meta.page_start);
    const anchor =
        url && url.toLowerCase().endsWith(".pdf") && Number.isFinite(page) && page > 0
            ? `#page=${page}`
            : "";

    return url ? url + anchor : null;
}

// 해시/쿼리 제거 후 확장자 판별
function isPdfUrl(u) {
    const base = (u || "").split("#")[0].split("?")[0];
    return !!base && base.toLowerCase().endsWith(".pdf");
}

export default function DocViewer({ source }) {
    const [finalUrl, setFinalUrl] = useState(null);

    const title = useMemo(() => {
        return source ? (source.doc_title || source.doc_id || "문서") : "문서 미리보기";
    }, [source]);

    useEffect(() => {
        if (!source) {
            setFinalUrl(null);
            return;
        }
        const url = buildDocUrl(source);
        setFinalUrl(url || null);
        // 필요시 디버깅:
        // console.debug("[DocViewer] finalUrl=", url);
    }, [source]);

    const isPdf = isPdfUrl(finalUrl);

    return (
        <div className="viewer">
            <div className="viewer__header">
                <div className="viewer__title">{title}</div>
                {finalUrl && (
                    <a href={finalUrl} target="_blank" rel="noreferrer" className="viewer__open">
                        새 탭으로 열기
                    </a>
                )}
            </div>

            <div className="viewer__body">
                {finalUrl ? (
                    isPdf ? (
                        <iframe src={finalUrl} title={title} />
                    ) : (
                        <div className="viewer__empty">
                            이 형식은 미리보기가 어렵습니다.{" "}
                            <a href={finalUrl} target="_blank" rel="noreferrer">
                                새 탭으로 열기
                            </a>
                        </div>
                    )
                ) : (
                    <div className="viewer__empty">문서 URL이 있을 때 미리보기가 표시됩니다.</div>
                )}
            </div>
        </div>
    );
}
