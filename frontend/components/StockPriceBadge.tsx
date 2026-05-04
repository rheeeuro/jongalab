"use client";

import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface PriceData {
  ticker: string;
  price: number;
  change: number;
  change_percent: number;
}

export function StockPriceBadge({ ticker }: { ticker: string }) {
  const [data, setData] = useState<PriceData | null>(null);
  const [loading, setLoading] = useState(Boolean(ticker));

  useEffect(() => {
    if (!ticker) return;
    
    // 백엔드 API 호출하여 실시간 주가 가져오기
    fetch(`/api/stock-price/${ticker}`)
      .then((res) => res.json())
      .then((json) => {
        if (!json.error) setData(json);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [ticker]);

  if (!ticker) return null;
  if (loading) return <span className="ml-3 text-xs text-slate-400 animate-pulse">실시간 가격 조회 중...</span>;
  if (!data) return null;

  const formatPrice = (price: number, currentTicker: string) => {
    // 한국 주식 (.KS 또는 .KQ 로 끝나는 경우)
    if (currentTicker.endsWith('.KS') || currentTicker.endsWith('.KQ')) {
      // 원화는 소수점 없이 ₩ 표시
      return `₩${price.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}`;
    }
    // 미국 주식 (그 외)
    // 달러는 소수점 2자리까지 $ 표시
    return `$${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  // 상승, 하락, 보합에 따른 색상 및 아이콘 결정 (한국 주식 시장 국룰: 빨간색 상승, 파란색 하락)
  const isUp = data.change_percent > 0;
  const isDown = data.change_percent < 0;
  const colorClass = isUp 
    ? "text-red-600 bg-red-50 border-red-200 dark:text-red-400 dark:bg-red-900/30 dark:border-red-800" 
    : isDown 
    ? "text-blue-600 bg-blue-50 border-blue-200 dark:text-blue-400 dark:bg-blue-900/30 dark:border-blue-800" 
    : "text-slate-600 bg-slate-50 border-slate-200 dark:text-slate-400 dark:bg-slate-800 dark:border-slate-700";
  
  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-sm font-semibold border ${colorClass}`}>
      {formatPrice(data.price, data.ticker)}
      <Icon className="w-4 h-4 mx-1" />
      {isUp ? "+" : ""}{data.change_percent.toFixed(2)}%
    </span>
  );
}