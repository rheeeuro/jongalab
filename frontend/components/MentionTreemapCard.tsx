"use client";

import { MentionStats } from "@/types";
import { Flame } from "lucide-react";
import { useMemo } from "react";
import { ResponsiveContainer, Treemap, Tooltip } from "recharts";

interface TreemapNode {
  [key: string]: unknown;
  name: string;
  size?: number;
  sector?: string;
  ticker?: string;
  avgSentiment?: number | null;
  fill?: string;
  stroke?: string;
  children?: TreemapNode[];
}

interface TreemapPayload {
  root?: { name?: string };
  name?: string;
  size?: number;
  sector?: string;
  ticker?: string;
  avgSentiment?: number | null;
  depth?: number;
}

interface ContentProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
  depth?: number;
  name?: string;
  sector?: string;
  ticker?: string;
  avgSentiment?: number | null;
  fill?: string;
  stroke?: string;
}

const MAX_TICKERS = 20;

// 섹터별 팔레트 (Tailwind 계열 — 명도 비슷, 색상만 분산)
const SECTOR_PALETTE: { fill: string; border: string }[] = [
  { fill: "#6366f1", border: "#4338ca" }, // indigo
  { fill: "#10b981", border: "#047857" }, // emerald
  { fill: "#f59e0b", border: "#b45309" }, // amber
  { fill: "#ec4899", border: "#be185d" }, // pink
  { fill: "#06b6d4", border: "#0e7490" }, // cyan
  { fill: "#8b5cf6", border: "#6d28d9" }, // violet
  { fill: "#ef4444", border: "#b91c1c" }, // red
  { fill: "#84cc16", border: "#4d7c0f" }, // lime
  { fill: "#f97316", border: "#c2410c" }, // orange
  { fill: "#14b8a6", border: "#0f766e" }, // teal
];

function sectorColor(index: number) {
  return SECTOR_PALETTE[index % SECTOR_PALETTE.length];
}

function sentimentDot(score: number | null | undefined): string {
  if (score == null) return "#cbd5e1"; // slate-300
  if (score >= 60) return "#dc2626";   // red-600 (강한 매수)
  if (score <= 40) return "#2563eb";   // blue-600 (강한 매도)
  return "#fbbf24";                    // amber-400 (중립)
}

function TreemapContent(props: ContentProps) {
  const { x = 0, y = 0, width = 0, height = 0, depth = 0, name, ticker, avgSentiment, fill, stroke } = props;

  if (depth === 1) {
    // 섹터 컨테이너 — 진한 외곽선만 (속은 children이 덮음)
    return (
      <g>
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          fill="transparent"
          stroke={stroke || "#475569"}
          strokeWidth={3}
        />
      </g>
    );
  }

  // 티커 박스
  if (depth === 2 && width > 0 && height > 0) {
    const tileFill = fill || "#94a3b8";
    const tileStroke = stroke || "#fff";
    const showLabel = width > 50 && height > 28;
    const dotR = Math.min(5, Math.max(3, width / 30));
    return (
      <g>
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          fill={tileFill}
          fillOpacity={0.92}
          stroke={tileStroke}
          strokeWidth={2}
        />
        {/* 감성 인디케이터 — 우상단 점 */}
        {width > 36 && height > 24 && (
          <circle
            cx={x + width - dotR - 4}
            cy={y + dotR + 4}
            r={dotR}
            fill={sentimentDot(avgSentiment ?? null)}
            stroke="#fff"
            strokeWidth={1}
          />
        )}
        {showLabel && (
          <>
            <text
              x={x + width / 2}
              y={y + height / 2 - 2}
              textAnchor="middle"
              fill="#fff"
              fontSize={width > 110 ? 13 : 11}
              fontWeight={700}
              style={{ pointerEvents: "none", textShadow: "0 1px 2px rgba(0,0,0,0.35)" }}
            >
              {name}
            </text>
            {height > 44 && (
              <text
                x={x + width / 2}
                y={y + height / 2 + 14}
                textAnchor="middle"
                fill="rgba(255,255,255,0.9)"
                fontSize={10}
                style={{ pointerEvents: "none" }}
              >
                {ticker}
              </text>
            )}
          </>
        )}
      </g>
    );
  }
  return null;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: { payload: TreemapPayload }[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || !payload.length) return null;
  const node = payload[0].payload;
  if (!node || node.depth === 0 || !node.name) return null;
  return (
    <div className="bg-white dark:bg-slate-800 p-3 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 text-xs">
      <p className="font-bold text-slate-800 dark:text-slate-100">{node.name}</p>
      {node.ticker && (
        <p className="text-slate-500 dark:text-slate-400 mt-0.5">티커: {node.ticker}</p>
      )}
      {node.sector && (
        <p className="text-slate-500 dark:text-slate-400 mt-0.5">섹터: {node.sector}</p>
      )}
      {typeof node.size === "number" && (
        <p className="text-slate-700 dark:text-slate-200 mt-1 font-semibold">
          언급 {node.size}건
        </p>
      )}
      {typeof node.avgSentiment === "number" && (
        <p className="mt-0.5" style={{ color: sentimentDot(node.avgSentiment) }}>
          평균 감성 {node.avgSentiment}
        </p>
      )}
    </div>
  );
}

export function MentionTreemapCard({ stats }: { stats: MentionStats | null }) {
  const { treemapData, legend } = useMemo<{
    treemapData: TreemapNode[];
    legend: { sector: string; color: string; mention_count: number }[];
  }>(() => {
    if (!stats || !stats.sectors?.length) {
      return { treemapData: [], legend: [] };
    }

    // 트리맵에 표시할 ticker 상위 N개 화이트리스트
    const allTickers = stats.sectors.flatMap((s) =>
      s.tickers.map((t) => ({ ...t, sector: s.sector }))
    );
    allTickers.sort((a, b) => b.mention_count - a.mention_count);
    const keep = new Set(
      allTickers.slice(0, MAX_TICKERS).map((t) => `${t.sector}::${t.ticker}`),
    );

    // 섹터는 mention_count 큰 순으로 팔레트 인덱스 부여
    const sortedSectors = [...stats.sectors].sort(
      (a, b) => b.mention_count - a.mention_count,
    );

    const treemap: TreemapNode[] = [];
    const legendList: { sector: string; color: string; mention_count: number }[] = [];

    sortedSectors.forEach((s, idx) => {
      const palette = sectorColor(idx);
      legendList.push({
        sector: s.sector,
        color: palette.fill,
        mention_count: s.mention_count,
      });
      const kept = s.tickers.filter((t) => keep.has(`${s.sector}::${t.ticker}`));
      if (!kept.length) return;
      treemap.push({
        name: s.sector,
        stroke: palette.border,
        children: kept.map((t) => ({
          name: t.name || t.ticker,
          ticker: t.ticker,
          sector: s.sector,
          size: t.mention_count,
          avgSentiment: t.avg_sentiment ?? null,
          fill: palette.fill,
          stroke: palette.border,
        })),
      });
    });

    return { treemapData: treemap, legend: legendList };
  }, [stats]);

  return (
    <div className="rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-6">
      <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-2">
        <h2 className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
          <Flame className="h-5 w-5 text-orange-500" />
          지금 뜨는 기업 · 최근 {stats?.window_hours ?? 24}시간
        </h2>
        {stats && (
          <span className="text-xs text-slate-500 dark:text-slate-400">
            콘텐츠 {stats.total_contents}건 · 언급 {stats.total_mentions}건
            {stats.dropped_unmapped_count > 0 && (
              <span className="ml-1 opacity-70">(섹터 미매핑 {stats.dropped_unmapped_count}건 제외)</span>
            )}
          </span>
        )}
      </div>

      {!stats || treemapData.length === 0 ? (
        <div className="h-40 flex items-center justify-center text-sm text-slate-400">
          최근 24시간 동안 분류 가능한 콘텐츠가 없습니다.
        </div>
      ) : (
        <>
          {/* 섹터 범례 */}
          <div className="flex flex-wrap gap-1.5 mb-3">
            {legend.map((l) => (
              <span
                key={l.sector}
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200"
              >
                <span
                  className="inline-block w-2.5 h-2.5 rounded-sm"
                  style={{ backgroundColor: l.color }}
                />
                {l.sector}
                <span className="text-slate-400 dark:text-slate-500">{l.mention_count}</span>
              </span>
            ))}
          </div>

          <div className="h-[320px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <Treemap
                data={treemapData}
                dataKey="size"
                stroke="#fff"
                isAnimationActive={false}
                content={<TreemapContent />}
              >
                <Tooltip content={<CustomTooltip />} />
              </Treemap>
            </ResponsiveContainer>
          </div>

          {/* 감성 점 범례 */}
          <div className="flex items-center gap-3 mt-3 text-[11px] text-slate-500 dark:text-slate-400">
            <span className="flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-600" /> 매수 우세
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-400" /> 중립
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-600" /> 매도 우세
            </span>
            <span className="ml-auto opacity-60">우상단 점이 평균 감성을 나타냅니다</span>
          </div>
        </>
      )}
    </div>
  );
}
