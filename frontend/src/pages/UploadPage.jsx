import React, { useEffect, useRef, useState, useCallback } from "react";
import {
    FaFileUpload,
    FaCheckCircle,
    FaExclamationCircle,
    FaSpinner,
    FaFileAlt,
    FaTrash,
    FaLock,
    FaInfoCircle
} from "react-icons/fa";

import { get, docsApi } from "../api/http.js";
import { me as fetchMe } from "../store/auth.js";

import "./UploadPage.css";

// 상수 정의
const STATUS_POLL_INTERVAL_MS = 1500; // 상태 폴링 간격
const MAX_UPLOAD_SECURITY_LEVEL = 3;  // 업로드 허용 최대 보안등급

/* 상태 표시 */
const StatusDisplay = ({ status, job, isSubmitting }) => {
    // 진행률 계산
    const getProgress = () => {
        if (!status || !status.total || status.total === 0) return 0;
        return Math.round((status.processed / status.total) * 100);
    };

    // ✅ 버튼 클릭 직후 (서버 응답 대기 중)
    if (isSubmitting && !job && !status) {
        return (
            <div className="status-item info">
                <div className="status-icon"><FaSpinner className="fa-spin" /></div>
                <div className="status-content">
                    <h4>파일 전송 중...</h4>
                    <p>서버로 파일을 전송하고 있습니다. 잠시만 기다려주세요.</p>
                </div>
            </div>
        );
    }

    if (!status && !job) {
        return (
            <div className="status-item info">
                <div className="status-icon"><FaFileAlt /></div>
                <div className="status-content">
                    <h4>대기 중</h4>
                    <p>업로드할 파일을 선택한 뒤 업로드를 시작하세요.</p>
                </div>
            </div>
        );
    }
    if (job && !status) {
        return (
            <div className="status-item info">
                <div className="status-icon"><FaSpinner className="fa-spin" /></div>
                <div className="status-content">
                    <h4>업로드 접수됨</h4>
                    <p>{job.accepted}개의 파일이 대기열에 추가되었습니다. 잠시 후 인덱싱이 시작됩니다.</p>
                </div>
            </div>
        );
    }
    if (status?.status === "pending") {
        return (
            <div className="status-item info">
                <div className="status-icon"><FaSpinner className="fa-spin" /></div>
                <div className="status-content">
                    <h4>대기 중</h4>
                    <p>작업이 곧 시작됩니다. 잠시만 기다려주세요.</p>
                </div>
            </div>
        );
    }
    if (status?.status === "running") {
        const progress = getProgress();
        return (
            <div className="status-item processing">
                <div className="status-icon"><FaSpinner className="fa-spin" /></div>
                <div className="status-content">
                    <h4>인덱싱 작업 중… {progress}%</h4>
                    <p>총 {status.total ?? "-"}개 중 {status.processed ?? 0}개 처리 완료</p>
                    <div className="progress-bar-container">
                        <div
                            className="progress-bar-fill"
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                </div>
            </div>
        );
    }
    if (status?.status === "succeeded") {
        return (
            <div className="status-item success">
                <div className="status-icon"><FaCheckCircle /></div>
                <div className="status-content">
                    <h4>업로드 성공</h4>
                    <p>모든 파일의 인덱싱이 완료되었습니다. 이제 검색에서 사용할 수 있습니다.</p>
                    <div className="progress-bar-container">
                        <div className="progress-bar-fill complete" style={{ width: '100%' }} />
                    </div>
                </div>
            </div>
        );
    }
    if (status?.status === "failed") {
        return (
            <div className="status-item error">
                <div className="status-icon"><FaExclamationCircle /></div>
                <div className="status-content">
                    <h4>업로드 실패</h4>
                    <p>{status.message || "처리 중 오류가 발생했습니다."}</p>
                </div>
            </div>
        );
    }
    return null;
};

export default function UploadPage() {
    const [files, setFiles] = useState([]);
    const [job, setJob] = useState(null);
    const [status, setStatus] = useState(null);
    const [user, setUser] = useState(null);
    const [errorMsg, setErrorMsg] = useState("");
    const [isDragOver, setIsDragOver] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false); // 버튼 클릭 즉시 블로킹용
    const timerRef = useRef(null);
    const fileInputRef = useRef(null);

    const isLoggedIn = !!user;
    // ✅ 업로드 허용 등급: 1~3 허용, 4(차단)는 불가
    const canUploadByLevel = isLoggedIn && Number(user?.security_level) <= MAX_UPLOAD_SECURITY_LEVEL;
    const isUploading = isSubmitting || status?.status === "running" || status?.status === "pending" || (job && !status);
    const disabled = !canUploadByLevel || isUploading; // 비로그인 or 4등급 or 업로딩 중

    // 진행 중인 업로드 작업 복원
    const restoreActiveJobs = useCallback(async () => {
        try {
            const result = await docsApi.activeJobs();
            const jobs = result?.jobs || [];

            if (jobs.length > 0) {
                const activeJob = jobs[0];
                setJob({ job_id: activeJob.job_id, accepted: activeJob.total });
                pollStatus(activeJob.job_id);
            }
        } catch {
            // 복원 실패는 무시 (새로 업로드하면 됨)
        }
    }, []);

    useEffect(() => {
        (async () => {
            try {
                const userData = await fetchMe();
                setUser(userData);

                // 로그인된 사용자인 경우 진행 중인 작업 복원
                if (userData) {
                    await restoreActiveJobs();
                }
            } catch {
                setUser(null);
            }
        })();

        // ⬇ 로그인/로그아웃 시 페이지 새로고침
        const onAuthChanged = () => window.location.reload();
        const onStorage = (e) => {
            if (e.key === "auth_token") onAuthChanged();
        };
        window.addEventListener("auth:changed", onAuthChanged);
        window.addEventListener("storage", onStorage);

        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
            window.removeEventListener("auth:changed", onAuthChanged);
            window.removeEventListener("storage", onStorage);
        };
    }, [restoreActiveJobs]);

    const pollStatus = async (job_id) => {
        // 기존 폴링 정리
        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }

        // ✅ 서버 응답 받았으면 submitting 해제 (job이 생성됨)
        setIsSubmitting(false);

        // 즉시 첫 번째 상태 조회 (폴링 시작 전)
        try {
            const initialStat = await get(`/docs/${encodeURIComponent(job_id)}/status`);
            setStatus(initialStat);
            if (initialStat.status === "succeeded" || initialStat.status === "failed") {
                setFiles([]);
                setJob(null);
                return;
            }
        } catch {
            // 초기 상태 조회 실패는 무시
        }

        // 이후 주기적 폴링
        timerRef.current = setInterval(async () => {
            try {
                const stat = await get(`/docs/${encodeURIComponent(job_id)}/status`);
                setStatus(stat);
                if (stat.status === "succeeded" || stat.status === "failed") {
                    clearInterval(timerRef.current);
                    timerRef.current = null;
                    setFiles([]);
                    setJob(null);
                }
            } catch {
                setErrorMsg("상태를 가져오는 데 실패했습니다.");
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
        }, STATUS_POLL_INTERVAL_MS);
    };

    const upload = async () => {
        if (!canUploadByLevel) return;
        if (files.length === 0) {
            setErrorMsg("업로드할 파일을 선택해주세요.");
            return;
        }

        // ✅ 버튼 클릭 즉시 블로킹 (네트워크 요청 전에!)
        setIsSubmitting(true);
        setJob(null); setStatus(null); setErrorMsg("");

        const formData = new FormData();
        files.forEach((f) => formData.append("files", f));
        formData.append("visibility", "public");

        try {
            const result = await docsApi.upload(formData);

            setJob(result);
            if (result?.job_id) pollStatus(result.job_id);
        } catch (err) {
            // 💡 413 에러 코드를 확인하는 로직 추가
            if (err.status === 413) {
                setErrorMsg("업로드 용량이 너무 큽니다. 한 번에 100MB 이하로 업로드해주세요.");
            } else {
                setErrorMsg(err?.message || "파일 업로드에 실패했습니다.");
            }
            // ❌ 에러 시 블로킹 해제
            setIsSubmitting(false);
        }
    };

    const addFiles = (newFiles) => {
        if (!canUploadByLevel) return; // 안전장치
        setFiles((prev) => {
            const combined = [...prev, ...newFiles];
            return Array.from(new Map(combined.map((f) => [f.name, f])).values());
        });
    };

    const onPick = (e) => {
        if (!canUploadByLevel) return;
        const picked = Array.from(e.target.files || []);
        addFiles(picked);
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const handleDragOver = (e) => {
        e.preventDefault(); e.stopPropagation();
        if (!canUploadByLevel) return;
        setIsDragOver(true);
    };
    const handleDragLeave = (e) => {
        e.preventDefault(); e.stopPropagation();
        if (!canUploadByLevel) return;
        setIsDragOver(false);
    };
    const handleDrop = (e) => {
        e.preventDefault(); e.stopPropagation();
        if (!canUploadByLevel) return;
        setIsDragOver(false);
        const dropped = Array.from(e.dataTransfer.files || []);
        if (dropped.length > 0) addFiles(dropped);
    };

    const removeFile = (name) => setFiles((fs) => fs.filter((f) => f.name !== name));

    const showLoginGuard = !isLoggedIn;
    const showLevelGuard = isLoggedIn && !canUploadByLevel; // (= 4등급)

    return (
        <div className="upload-page">
            <h2>문서 업로드</h2>

            <div className="info-banner">
                <FaInfoCircle />
                <p>
                    <strong>PDF 형식의 파일을 권장합니다.</strong>
                    <br />
                    PDF로 업로드 시, 문서 미리보기가 가능해 품질 좋은 답변을 얻을 수 있습니다.
                    <br />
                    <strong>한 번에 100MB까지 업로드할 수 있습니다.</strong>
                </p>
            </div>

            {/* 🔒 가드 배너 */}
            {showLoginGuard && (
                <div className="guard-banner">
                    <FaLock />
                    <div>
                        <strong>로그인이 필요합니다.</strong>
                        <div>로그인 후 업로드 기능을 이용할 수 있어요.</div>
                    </div>
                </div>
            )}
            {showLevelGuard && (
                <div className="guard-banner">
                    <FaLock />
                    <div>
                        <strong>권한이 부족합니다.</strong>
                        <div>보안등급 1–3 사용자만 업로드할 수 있어요.</div>
                    </div>
                </div>
            )}

            {/* 드랍존 카드 */}
            <div className="section">
                <div className={`card dropzone-card ${disabled ? "is-disabled" : ""}`}>
                    {/* 잠금 오버레이 */}
                    {disabled && (
                        <div className="blocked-overlay">
                            <FaLock />
                            <div className="blocked-text">
                                {isUploading ? "업로드 처리 중입니다... 잠시만 기다려주세요." :
                                    showLoginGuard ? "로그인 후 이용 가능합니다" : "업로드 권한이 없습니다"}
                            </div>
                        </div>
                    )}

                    <label className="file-input-label">
                        <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            onChange={onPick}
                            disabled={disabled}
                            accept=".pdf,.docx,.txt,.html,.md,.csv,.pptx"
                        />
                        📂 파일 추가
                    </label>

                    <div
                        className={`dropzone ${isDragOver ? "is-dragover" : ""} ${disabled ? "is-blocked" : ""}`}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                    >
                        {files.length === 0 ? (
                            <div className="dropzone-placeholder">
                                <FaFileUpload />
                                <p>여기로 파일을 끌어다 놓으세요.</p>
                            </div>
                        ) : (
                            <div className="file-list">
                                {files.map((f) => (
                                    <div key={f.name} className="file-item">
                                        <span className="file-name">{f.name}</span>
                                        <button className="remove-btn" onClick={() => removeFile(f.name)} disabled={isUploading}>
                                            <FaTrash />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="button-area">
                        <button className="btn btn-primary" onClick={upload} disabled={disabled || files.length === 0}>
                            {isUploading ? "처리 중..." : `파일 ${files.length}개 업로드`}
                        </button>
                    </div>
                </div>
            </div>

            {/* 상태 카드 */}
            <div className="section status-section">
                <h3>업로드 상태</h3>
                <div className="card">
                    <div className="status-box">
                        <StatusDisplay status={status} job={job} isSubmitting={isSubmitting} />
                    </div>
                </div>
            </div>

            {/* 서버/클라이언트 오류 배너 */}
            {errorMsg && <div className="error-banner">{errorMsg}</div>}
        </div>
    );
}
