// qa-test.js (질문-답변 테스트용)
import ws from 'k6/ws';
import { check } from 'k6';
import { Trend } from 'k6/metrics'; // 💡 시간 측정을 위한 Trend metric 추가
import { Rate } from 'k6/metrics';  // 💡 성공률 측정을 위한 Rate metric 추가

// 💡 사용자 정의 측정 지표 생성
const answerTime = new Trend('answer_time');
const successRate = new Rate('success_rate');

// 테스트 옵션: 5명의 가상 유저가 1분 동안 테스트를 반복합니다.
export const options = {
    vus: 10,
    duration: '2m',
};

export default function () {
    const url = 'ws://192.68.10.249:8082/api/chat/';

    // 💡 ws.connect를 Promise로 감싸서 비동기 응답을 기다립니다.
    const promise = new Promise((resolve, reject) => {
        // 15초 이상 답변이 없으면 실패로 간주하고 연결을 종료합니다 (Timeout)
        const timeout = setTimeout(() => {
            reject('WebSocket response timed out');
        }, 200000); // 💡 평균 답변 시간(13초)보다 넉넉하게 설정

        const res = ws.connect(url, {}, function (socket) {
            let startTime;

            socket.on('open', () => {
                // 💡 연결이 열리면 질문을 딱 한 번 보냅니다.
                startTime = new Date().getTime();
                socket.send("안녕하세요, 출장 여비 규정에 대해 알려주세요.");
            });

            socket.on('message', (data) => {
                // 💡 답변을 받으면,
                clearTimeout(timeout); // 타임아웃을 해제하고,
                const endTime = new Date().getTime();
                const duration = endTime - startTime;

                answerTime.add(duration);  // 답변 시간을 기록하고,
                successRate.add(1);        // 성공으로 처리합니다 (1 = true).

                socket.close();            // 할 일이 끝났으니 연결을 닫고,
                resolve();                 // Promise를 성공으로 완료합니다.
            });

            socket.on('close', () => {
                // console.log('WebSocket connection closed.');
            });

            socket.on('error', (e) => {
                // 에러가 발생하면 실패로 간주합니다.
                clearTimeout(timeout);
                successRate.add(0); // 0 = false
                reject(e.error());
            });
        });

        check(res, { 'WebSocket handshake successful': (r) => r && r.status === 101 });

    }).catch(error => {
        // Promise가 reject (실패)되면 콘솔에 에러를 찍습니다.
        // console.error(error);
    });
}