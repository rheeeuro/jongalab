"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type CandlestickData,
  type UTCTimestamp,
} from "lightweight-charts";

interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  extended?: boolean; // 정규장 밖(프리/애프터) 봉 — 흐리게 표시
}

// 한국식 색(상승=빨강, 하락=파랑). 정규장 밖 봉은 채도를 낮춰 구분.
const UP = "#ef4444";
const DOWN = "#3b82f6";
const UP_EXT = "#fca5a5";
const DOWN_EXT = "#93c5fd";

function toTimestamp(timeStr: string): UTCTimestamp {
  // "2025-09-17T13:20" → UTC timestamp (seconds)
  // lightweight-charts는 UTC 기준으로 표시하므로,
  // KST 시간값을 그대로 UTC로 넣어 차트에 한국 시간이 보이게 함
  const [datePart, timePart] = timeStr.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute] = timePart.split(":").map(Number);
  return (Date.UTC(year, month - 1, day, hour, minute, 0) / 1000) as UTCTimestamp;
}

export function CandlestickChart({
  data,
  initialRangeDays = 7,
  fit = false,
}: {
  data: CandleData[];
  initialRangeDays?: number;
  fit?: boolean; // true 면 가져온 전 구간을 꽉 차게(분봉 시장 차트용). false 면 최근 N일 줌.
}) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current || !data.length) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const isDark = document.documentElement.classList.contains("dark");

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 400,
      layout: {
        background: { color: isDark ? "#0f172a" : "#ffffff" },
        textColor: isDark ? "#94a3b8" : "#64748b",
      },
      grid: {
        vertLines: { color: isDark ? "#1e293b" : "#f1f5f9" },
        horzLines: { color: isDark ? "#1e293b" : "#f1f5f9" },
      },
      crosshair: { mode: 0 },
      rightPriceScale: {
        borderColor: isDark ? "#334155" : "#e2e8f0",
      },
      timeScale: {
        borderColor: isDark ? "#334155" : "#e2e8f0",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // 캔들스틱 시리즈 (한국식: 상승=빨강, 하락=파랑). 정규장 밖 봉은 per-bar 색으로 흐리게.
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
    });

    const candleData: CandlestickData<UTCTimestamp>[] = data.map((d) => {
      const up = d.close >= d.open;
      const base = { time: toTimestamp(d.time), open: d.open, high: d.high, low: d.low, close: d.close };
      if (!d.extended) return base;
      const col = up ? UP_EXT : DOWN_EXT;
      return { ...base, color: col, borderColor: col, wickColor: col };
    });

    candleSeries.setData(candleData);

    // 거래량 히스토그램
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const volumeData = data.map((d) => {
      const up = d.close >= d.open;
      const opacity = d.extended ? 0.12 : 0.3; // 정규장 밖 봉은 더 흐리게
      return {
        time: toTimestamp(d.time),
        value: d.volume,
        color: up ? `rgba(239, 68, 68, ${opacity})` : `rgba(59, 130, 246, ${opacity})`,
      };
    });

    volumeSeries.setData(volumeData);

    // 이동평균선 (5, 10, 20)
    const maColors = ["#f59e0b", "#8b5cf6", "#10b981"];
    const maPeriods = [5, 10, 20];

    maPeriods.forEach((period, idx) => {
      const maData = [];
      for (let i = period - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) {
          sum += data[i - j].close;
        }
        maData.push({
          time: toTimestamp(data[i].time),
          value: sum / period,
        });
      }

      const maSeries = chart.addSeries(LineSeries, {
        color: maColors[idx],
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      maSeries.setData(maData);
    });

    // 초기 줌: fit 이면 가져온 전 구간을 꽉 차게(분봉 시장 차트), 아니면 최근 initialRangeDays 일치.
    if (fit) {
      chart.timeScale().fitContent();
    } else {
      const lastTime = candleData[candleData.length - 1].time;
      const rangeStart = lastTime - initialRangeDays * 24 * 60 * 60;
      chart.timeScale().setVisibleRange({
        from: rangeStart as UTCTimestamp,
        to: lastTime as UTCTimestamp,
      });
    }

    const container = chartContainerRef.current;
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || !chartRef.current) return;
      const { width } = entries[0].contentRect;
      chartRef.current.applyOptions({ width });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [data, initialRangeDays, fit]);

  if (!data.length) {
    return (
      <p className="text-sm text-slate-400 text-center py-8">
        차트로 보여줄 자료가 없어요
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div ref={chartContainerRef} className="w-full rounded-lg overflow-hidden" />
      <div className="flex items-center gap-4 text-xs text-slate-500 px-1">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 bg-amber-500 rounded" /> 5MA
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 bg-violet-500 rounded" /> 10MA
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 bg-emerald-500 rounded" /> 20MA
        </span>
        <span className="ml-auto flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 bg-red-500 rounded-sm" /> 상승
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 bg-blue-500 rounded-sm" /> 하락
          </span>
        </span>
      </div>
    </div>
  );
}
