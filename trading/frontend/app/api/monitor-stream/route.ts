import { NextRequest } from "next/server";
import { API_BASE, authHeaders } from "@/lib/api";

// GET /api/monitor-stream — 모니터 탭 실시간 시세 SSE 프록시 (:8002 `/monitor/stream`).
// 브라우저는 :8002 에 직접 못 붙으므로(127.0.0.1 바인딩) Next 가 스트림을 그대로 중계한다.
// req.signal 을 그대로 넘겨 브라우저가 연결을 끊으면 상류 요청도 취소된다 —
// 그래야 백엔드가 구독자를 반납하고, 마지막 구독자면 키움 WS 세션을 닫는다.
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    const res = await fetch(`${API_BASE}/monitor/stream`, {
      headers: { ...(await authHeaders()), Accept: "text/event-stream" },
      signal: req.signal,
      cache: "no-store",
    });
    if (!res.ok || !res.body) {
      return new Response("upstream error", { status: res.status || 502 });
    }
    return new Response(res.body, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error) {
    if (req.signal.aborted) return new Response(null, { status: 204 }); // 정상 이탈
    console.error("monitor-stream 프록시 에러:", error);
    return new Response("stream error", { status: 500 });
  }
}
