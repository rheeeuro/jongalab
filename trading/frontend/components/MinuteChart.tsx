"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type CandlestickData,
  type SeriesMarker,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Candle, ChartMarker } from "@/types";

// "2026-06-26T15:31"(또는 :SS 포함) → UTC 타임스탬프(초). KST 시각을 그대로 UTC 로 넣어
// 차트에 한국 시간이 보이게 한다(jongalab CandlestickChart 와 동일 규약).
function toTimestamp(timeStr: string): UTCTimestamp {
  const [datePart, timePart] = timeStr.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  const [hh, mm] = timePart.split(":").map(Number);
  return (Date.UTC(y, m - 1, d, hh, mm, 0) / 1000) as UTCTimestamp;
}

/** 1분봉 캔들 + 매수/매도 타점. 타점 시각은 가장 가까운 캔들로 스냅해 항상 봉 위에 찍히게 한다.
 *  한국식 색(상승=빨강·하락=파랑). 모바일 모달용으로 높이를 낮게(260) 쓴다. */
export default function MinuteChart({ candles, markers }: { candles: Candle[]; markers: ChartMarker[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;
    const el = containerRef.current;
    const isDark = document.documentElement.classList.contains("dark");

    const chart = createChart(el, {
      width: el.clientWidth,
      height: 260,
      layout: {
        background: { color: "transparent" },
        textColor: isDark ? "#94a3b8" : "#64748b",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: isDark ? "#1e293b" : "#f1f5f9" },
        horzLines: { color: isDark ? "#1e293b" : "#f1f5f9" },
      },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: isDark ? "#334155" : "#e2e8f0" },
      timeScale: {
        borderColor: isDark ? "#334155" : "#e2e8f0",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScale: { axisPressedMouseMove: false },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#ef4444",
      downColor: "#3b82f6",
      borderUpColor: "#ef4444",
      borderDownColor: "#3b82f6",
      wickUpColor: "#ef4444",
      wickDownColor: "#3b82f6",
    });
    const candleData: CandlestickData<UTCTimestamp>[] = candles.map((c) => ({
      time: toTimestamp(c.time),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeries.setData(candleData);

    // 거래량 히스토그램(하단 20%)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volumeSeries.setData(
      candles.map((c) => ({
        time: toTimestamp(c.time),
        value: c.volume,
        color: c.close >= c.open ? "rgba(239,68,68,0.3)" : "rgba(59,130,246,0.3)",
      }))
    );

    // 매수/매도 타점 — 각 타점 시각을 가장 가까운 캔들 시각으로 스냅(봉 사이/장외 시각도 봉 위에 표시).
    const times = candleData.map((c) => c.time as number);
    const snap = (iso: string): UTCTimestamp => {
      const t = toTimestamp(iso);
      let best = times[0];
      let bestDiff = Math.abs(times[0] - t);
      for (const ct of times) {
        const diff = Math.abs(ct - t);
        if (diff < bestDiff) {
          best = ct;
          bestDiff = diff;
        }
      }
      return best as UTCTimestamp;
    };
    const snapped = markers.map((mk) => ({ ...mk, t: snap(mk.time) }));
    const seriesMarkers: SeriesMarker<UTCTimestamp>[] = snapped
      .map((mk) => ({
        time: mk.t,
        position: mk.side === "buy" ? ("belowBar" as const) : ("aboveBar" as const),
        color: mk.side === "buy" ? "#ef4444" : "#3b82f6",
        shape: mk.side === "buy" ? ("arrowUp" as const) : ("arrowDown" as const),
        text: `${mk.side === "buy" ? "매수" : "매도"} ${mk.price.toLocaleString()}`,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));
    if (seriesMarkers.length) createSeriesMarkers(candleSeries, seriesMarkers);

    // 초기 줌: 매수/매도 타점 구간을 ±패딩으로 살짝 확대(타점 없으면 전체). 사용자는 자유롭게 줌아웃 가능.
    const idxs = snapped.map((m) => times.indexOf(m.t as number)).filter((i) => i >= 0);
    if (idxs.length) {
      const from = Math.min(...idxs);
      const to = Math.max(...idxs);
      const pad = Math.max(20, Math.round((to - from) * 0.5));
      chart.timeScale().setVisibleLogicalRange({
        from: Math.max(0, from - pad),
        to: Math.min(times.length - 1, to + pad),
      });
    } else {
      chart.timeScale().fitContent();
    }

    // 리사이즈 시 폭만 갱신 — 보이는 구간(초기 줌)은 lightweight-charts 가 그대로 유지한다.
    const ro = new ResizeObserver((entries) => {
      if (!entries.length || !chartRef.current) return;
      chartRef.current.applyOptions({ width: entries[0].contentRect.width });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, markers]);

  if (candles.length === 0) {
    return <p className="py-8 text-center text-sm text-slate-400">차트 데이터가 없어요.</p>;
  }
  return <div ref={containerRef} className="w-full" />;
}
