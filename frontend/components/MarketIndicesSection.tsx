"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import type { MarketIndices } from "@/types";
import { AnimatedMarketIndexCard } from "./AnimatedMarketIndexCard";
import { Globe, Landmark, Gem } from "lucide-react";

const CACHE_KEY = "market-indices-cache";
const POLL_INTERVAL = 60_000; // 1분
const EMPTY_INDICES: MarketIndices = { US: [], KR: [], COMMODITIES: [] };

function readCachedMarketIndices(): MarketIndices | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
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
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-800 dark:text-slate-100">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

export function MarketIndicesSection({
  showUS,
  showKR,
}: {
  showUS: boolean;
  showKR: boolean;
}) {
  const [displayData, setDisplayData] = useState<MarketIndices>(() => {
    const cached = readCachedMarketIndices();
    return cached ?? EMPTY_INDICES;
  });
  const [animate, setAnimate] = useState(false);
  const hasCache = useRef(displayData !== EMPTY_INDICES);

  const animateTo = useCallback((next: MarketIndices) => {
    setAnimate(false);
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
        animateTo(data);
      } else {
        setDisplayData(data);
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
      {showUS && (
        <Section
          icon={<Globe className="h-5 w-5 text-blue-500" />}
          title="🇺🇸 미국 시장"
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {displayData.US.map((item) => (
              <AnimatedMarketIndexCard
                key={item.symbol}
                item={item}
                animate={animate}
              />
            ))}
          </div>
        </Section>
      )}

      {showKR && (
        <Section
          icon={<Landmark className="h-5 w-5 text-red-500" />}
          title="🇰🇷 한국 시장"
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {displayData.KR.map((item) => (
              <AnimatedMarketIndexCard
                key={item.symbol}
                item={item}
                animate={animate}
              />
            ))}
          </div>
        </Section>
      )}

      <Section
        icon={<Gem className="h-5 w-5 text-amber-500" />}
        title="원자재 / 암호화폐"
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {displayData.COMMODITIES.map((item) => (
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
