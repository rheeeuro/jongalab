"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import type { MarketIndices } from "@/types";
import { AnimatedMarketIndexCard } from "./AnimatedMarketIndexCard";
import { Landmark, Gem, Globe, TrendingUp } from "lucide-react";

const CACHE_KEY = "market-indices-cache";
const POLL_INTERVAL = 60_000; // 1분
const EMPTY_INDICES: MarketIndices = { US: [], KR: [], COMMODITIES: [], FUTURES: [] };

function readCachedMarketIndices(): MarketIndices | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/** 새 응답에서 값이 빈 카드는 화면(캐시)에 있던 마지막 값을 유지한다.
 * 서버도 마지막 정상값을 채우지만(백엔드 재기동 직후엔 그 값이 없다), 카드가
 * '데이터 없음'으로 깜빡이지 않게 하는 최종 방어선. */
function mergeKeepLast(prev: MarketIndices, next: MarketIndices): MarketIndices {
  const merged = { ...next } as MarketIndices;
  for (const key of Object.keys(next) as (keyof MarketIndices)[]) {
    const prevItems = prev[key] ?? [];
    merged[key] = (next[key] ?? []).map((item) => {
      if (item.price !== null) return item;
      const last = prevItems.find((p) => p.symbol === item.symbol);
      return last && last.price !== null ? last : item;
    });
  }
  return merged;
}

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-6">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

export function MarketIndicesSection() {
  const [displayData, setDisplayData] = useState<MarketIndices>(() => {
    const cached = readCachedMarketIndices();
    return cached ?? EMPTY_INDICES;
  });
  const [animate, setAnimate] = useState(false);
  const hasCache = useRef(displayData !== EMPTY_INDICES);
  // 빈 값 대체(mergeKeepLast)에 쓸 현재 표시값 — 폴링 콜백이 최신 값을 읽어야 한다.
  const latest = useRef(displayData);

  const animateTo = useCallback((next: MarketIndices) => {
    setAnimate(false);
    latest.current = next;
    // 1프레임: 현재 값 고정 → 2프레임: 새 값으로 전환
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setDisplayData(next);
        setAnimate(true);
      });
    });
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(next));
    } catch {
      // localStorage 용량 초과 또는 사용 불가
    }
  }, []);

  const fetchLatest = useCallback(async () => {
    try {
      const res = await fetch("/api/market-indices", { cache: "no-store" });
      if (!res.ok) return;
      const data: MarketIndices = await res.json();
      if (hasCache.current) {
        animateTo(mergeKeepLast(latest.current, data));
      } else {
        setDisplayData(data);
        latest.current = data;
        hasCache.current = true;
        try {
          localStorage.setItem(CACHE_KEY, JSON.stringify(data));
        } catch {
          // localStorage 용량 초과 또는 사용 불가
        }
      }
    } catch {
      // 네트워크 에러 무시, 다음 폴링에서 재시도
    }
  }, [animateTo]);

  // 캐시값을 먼저 보여주고, API 조회 결과는 슬롯머신 애니메이션으로 반영한다.
  useEffect(() => {
    const id = window.setTimeout(fetchLatest, 0);
    return () => window.clearTimeout(id);
  }, [fetchLatest]);

  // 1분마다 지표 API 폴링
  useEffect(() => {
    const id = setInterval(fetchLatest, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [fetchLatest]);

  return (
    <>
      <Section
        icon={<Globe className="h-5 w-5 text-blue-500" />}
        title="🇺🇸 미국 시장"
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {(displayData.US ?? []).map((item) => (
            <AnimatedMarketIndexCard
              key={item.symbol}
              item={item}
              animate={animate}
            />
          ))}
        </div>
      </Section>

      <Section
        icon={<Landmark className="h-5 w-5 text-red-500" />}
        title="🇰🇷 한국 시장"
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {(displayData.KR ?? []).map((item) => (
            <AnimatedMarketIndexCard
              key={item.symbol}
              item={item}
              animate={animate}
            />
          ))}
        </div>
      </Section>

      <Section
        icon={<TrendingUp className="h-5 w-5 text-emerald-500" />}
        title="📊 선물 (내일 갭 참고)"
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {(displayData.FUTURES ?? []).map((item) => (
            <AnimatedMarketIndexCard
              key={item.symbol}
              item={item}
              animate={animate}
            />
          ))}
        </div>
      </Section>

      <Section
        icon={<Gem className="h-5 w-5 text-amber-500" />}
        title="원자재 / 암호화폐"
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {(displayData.COMMODITIES ?? []).map((item) => (
            <AnimatedMarketIndexCard
              key={item.symbol}
              item={item}
              animate={animate}
            />
          ))}
        </div>
      </Section>
    </>
  );
}
