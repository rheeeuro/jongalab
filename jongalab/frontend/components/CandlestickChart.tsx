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
}

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
}: {
  data: CandleData[];
  initialRangeDays?: number;
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

    // 캔들스틱 시리즈 (한국식: 상승=빨강, 하락=파랑)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#ef4444",
      downColor: "#3b82f6",
      borderUpColor: "#ef4444",
      borderDownColor: "#3b82f6",
      wickUpColor: "#ef4444",
      wickDownColor: "#3b82f6",
    });

    const candleData: CandlestickData<UTCTimestamp>[] = data.map((d) => ({
      time: toTimestamp(d.time),
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    candleSeries.setData(candleData);

    // 거래량 히스토그램
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const volumeData = data.map((d) => ({
      time: toTimestamp(d.time),
      value: d.volume,
      color:
        d.close >= d.open
          ? "rgba(239, 68, 68, 0.3)"
          : "rgba(59, 130, 246, 0.3)",
    }));

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

    // 초기 줌: 최근 initialRangeDays 일치만 보이도록 (기본 7일)
    const lastTime = candleData[candleData.length - 1].time;
    const rangeStart = lastTime - initialRangeDays * 24 * 60 * 60;
    chart.timeScale().setVisibleRange({
      from: rangeStart as UTCTimestamp,
      to: lastTime as UTCTimestamp,
    });

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
  }, [data, initialRangeDays]);

  if (!data.length) {
    return (
      <p className="text-sm text-slate-400 text-center py-8">
        차트 데이터가 없습니다
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
