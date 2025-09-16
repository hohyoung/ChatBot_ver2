// frontend/src/components/DocViewer/DocViewer.jsx
import React, { useEffect, useMemo, useState } from "react";
import "./DocViewer.css";
import { absolute } from "../../api/http.js";

export default function DocViewer({ source }) {
    // source: { doc_title, doc_url, doc_relpath, ... }
    const [finalUrl, setFinalUrl] = useState(null);

    const title = useMemo(() => {
        return source ? (source.doc_title || source.doc_id || "문서") : "문서 미리보기";
    }, [source]);

    useEffect(() => {
        if (!source) {
            setFinalUrl(null);
            return;
        }

        // 1) 우선순위: doc_url → doc_relpath(public/면 파일명 뽑아서 /static/docs/...) → null
        let url = source.doc_url || null;
        if (!url && source.doc_relpath && String(source.doc_relpath).startsWith("public/")) {
            const parts = String(source.doc_relpath).split("/");
            const filename = parts[parts.length - 1];
            url = `/static/docs/${filename}`;
        }

        // 2) 항상 절대 URL로 보정 (여기가 핵심!)
        const abs = absolute(url);
        setFinalUrl(abs);

        // 디버깅에 도움:
        console.debug("[DocViewer] source=", source, "computed url=", url, "final=", abs);
    }, [source]);

    const isPDF = !!finalUrl && finalUrl.toLowerCase().includes(".pdf");

    return (
        <div className="viewer">
            <div className="viewer__header">
                <div className="viewer__title">{title}</div>
                {finalUrl && (
                    <a className="btn btn-ghost" href={finalUrl} target="_blank" rel="noreferrer">
                        새 탭에서 열기
                    </a>
                )}
            </div>

            <div className="viewer__body">
                {finalUrl ? (
                    isPDF ? (
                        <iframe src={finalUrl} title="document" />
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
