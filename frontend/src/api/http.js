// 작은 fetch 래퍼 (에러 처리 포함)
export async function http(method, url, body, headers = {}) {
    const init = { method, headers: { ...headers } };
    if (body instanceof FormData) {
        init.body = body; // form-data는 헤더 자동
    } else if (body !== undefined) {
        init.headers['Content-Type'] = 'application/json; charset=utf-8';
        init.body = JSON.stringify(body);
    }
    const res = await fetch(url, init);
    if (!res.ok) {
        let text = await res.text().catch(() => '');
        throw new Error(text || `HTTP ${res.status}`);
    }
    // 202 등도 JSON을 주므로 그냥 json 시도
    return res.json().catch(() => ({}));
}

export const get = (url) => http('GET', url);
export const post = (url, body) => http('POST', url, body);
