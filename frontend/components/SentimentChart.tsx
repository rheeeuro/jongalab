"use client";

import { ContentAnalysis } from "@/types";
import { useMemo } from "react";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from "recharts";

interface HistoryData {
  date: string;
  price: number;
}

interface ChartPoint {
  dateKey?: string;
  displayDate?: string;
  score?: number;
  price?: number;
  title?: string;
  count?: number;
  firstTitle?: string;
}

interface TooltipPayloadItem {
  name?: string;
  value?: number | string;
  color?: string;
  payload: ChartPoint;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
}

// 🎨 우리가 만든 예쁜 커스텀 툴팁 (메인/상세 공통 사용)
const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload; 
    
    return (
      <div className="bg-white dark:bg-slate-800 p-3 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 z-50">
        <p className="font-bold text-slate-800 dark:text-slate-200 mb-2">{label}</p>
        
        {payload.map((entry, index) => {
          const value = entry.value ?? "";
          const displayValue =
            entry.name === "실제 주가" && typeof value === "number"
              ? value.toLocaleString()
              : value;

          return (
          <p key={index} style={{ color: entry.color }} className="text-sm font-bold flex justify-between gap-4 mb-1">
            <span>{entry.name}</span>
            {/* 주가일 경우 $ 기호 추가, 점수일 경우 그냥 숫자 표시 */}
            <span>{displayValue}</span>
          </p>
          );
        })}
        
        {/* 뉴스 제목이 있으면 하단에 표시 */}
        {data.title && (
          <div className="mt-2 pt-2 border-t border-slate-100 dark:border-slate-700">
            <p className="text-xs text-slate-500 dark:text-slate-400 break-keep w-48 font-medium">
              {data.title}
            </p>
          </div>
        )}
      </div>
    );
  }
  return null;
};

export function SentimentChart({ 
  data, 
  history = [], 
  displayName = "" 
}: { 
  data: ContentAnalysis[], 
  history?: HistoryData[], 
  displayName?: string 
}) {
  
  const isDetailPage = history && history.length > 0;

  const chartData = useMemo(() => {
    // 📍 1. 메인 페이지 모드
    if (!isDetailPage) {
      const sortedData = [...data].reverse();
      return sortedData.map((item) => {
        const dateObj = new Date(item.created_at || "");
        const dateStr = `${dateObj.getMonth() + 1}/${dateObj.getDate()} ${dateObj.getHours()}:${String(dateObj.getMinutes()).padStart(2, '0')}`;
        return {
          displayDate: dateStr,
          score: item.sentiment_score ?? 50,
          title: item.title, // 원본 제목 그대로 사용
        };
      });
    }

    // 📍 2. 상세 페이지 모드 (날짜별 병합 + 제목 요약)
    const dateMap = new Map<string, ChartPoint>();

    // 주가 뼈대 잡기
    history.forEach((h) => {
      dateMap.set(h.date, { dateKey: h.date, price: h.price });
    });

    // 감성 점수와 뉴스 제목 병합하기
    data.forEach((item) => {
      const d = new Date(item.created_at || "");
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      const dateKey = `${y}-${m}-${day}`;
      
      const currentScore = item.sentiment_score ?? 50; 
      
      if (!dateMap.has(dateKey)) {
        // 🚀 처음 들어가는 뉴스면 제목(firstTitle)을 저장해 둡니다
        dateMap.set(dateKey, { 
          dateKey, 
          score: currentScore, 
          count: 1, 
          firstTitle: item.title 
        });
      } else {
        const existing = dateMap.get(dateKey);
        if (!existing) return;
        if (existing.score === undefined) {
          existing.score = currentScore;
          existing.count = 1;
          existing.firstTitle = item.title;
        } else {
          existing.score = Math.round((existing.score * existing.count + currentScore) / (existing.count + 1));
          existing.count += 1; // 🚀 뉴스가 추가될 때마다 카운트 증가
        }
      }
    });

    // 정렬 후 화면에 뿌릴 포맷으로 정리
    const sorted = Array.from(dateMap.values()).sort((a, b) => a.dateKey.localeCompare(b.dateKey));
    return sorted.map(item => {
      const parts = item.dateKey ? item.dateKey.split('-') : [];
      const displayDate = parts.length === 3 ? `${parseInt(parts[1])}/${parseInt(parts[2])}` : item.displayDate;
      
      // 🚀 핵심: 그날 뉴스가 여러 개면 "첫번째 기사 제목... 외 N건" 형태로 요약!
      let finalTitle = "";
      if (item.firstTitle) {
        finalTitle = item.firstTitle.length > 25 ? item.firstTitle.substring(0, 25) + "..." : item.firstTitle;
        if (item.count > 1) {
          finalTitle += ` (외 ${item.count - 1}건)`;
        }
      }

      return { 
        ...item, 
        displayDate,
        title: finalTitle // 조합된 제목을 title로 넘겨줍니다
      };
    });
  }, [data, history, isDetailPage]);

  if (chartData.length < 2) return null;

  return (
    <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm mb-8">
      <h3 className="text-lg font-bold mb-6 text-slate-800 dark:text-slate-100 flex items-center gap-2">
        {isDetailPage ? `📈 ${displayName} 여론 vs 실제 주가 흐름` : "📈 전체 AI 여론 (감성 점수) 변화 추이"}
      </h3>
      
      <div className="h-72 w-full text-xs">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="displayDate" tick={{ fill: '#64748b' }} axisLine={false} tickLine={false} />
            
            <YAxis yAxisId="left" domain={[0, 100]} tick={{ fill: '#64748b' }} axisLine={false} tickLine={false} />
            
            {isDetailPage && (
              <YAxis yAxisId="right" orientation="right" tick={{ fill: '#f59e0b' }} axisLine={false} tickLine={false} domain={['auto', 'auto']} />
            )}
            
            {/* 🚀 커스텀 툴팁 장착 완료! */}
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'transparent' }} />
            
            {isDetailPage && <Legend wrapperStyle={{ paddingTop: '20px' }} />}
            
            <Area yAxisId="left" type="monotone" dataKey="score" name="AI 감성 점수" stroke="#6366f1" fillOpacity={1} fill="url(#colorScore)" connectNulls={true} />
            
            {isDetailPage && (
              <Line yAxisId="right" type="monotone" dataKey="price" name="실제 주가" stroke="#f59e0b" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} connectNulls={true} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}