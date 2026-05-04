"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import type { MarketIndices } from "@/types";
import { AnimatedMarketIndexCard } from "./AnimatedMarketIndexCard";
import { Globe, Landmark, Gem } from "lucide-react";

const CACHE_KEY = "market-indices-cache";
const POLL_INTERVAL = 60_000; // 1분

function readCachedMarketIndices(fallback: MarketIndices): MarketIndices {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
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
  freshData,
  showUS,
  showKR,
}: {
  freshData: MarketIndices;
  showUS: boolean;
  showKR: boolean;
}) {
  const [displayData, setDisplayData] = useState<MarketIndices>(() =>
    readCachedMarketIndices(freshData)
  );
  const [animate, setAnimate] = useState(false);
  const initialized = useRef(false);
  const startedFromCache = useRef(displayData !== freshData);
  const latestData = useRef(freshData);

  const animateTo = useCallback((next: MarketIndices) => {
    latestData.current = next;
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

  // 캐시가 있으면 캐시값 먼저 보여주고 슬롯머신 애니메이션으로 전환
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (startedFromCache.current) {
      // 캐시가 있으면 paint 후 슬롯머신 애니메이션으로 전환
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setDisplayData(freshData);
          setAnimate(true);
        });
      });
    }
  }, [freshData]);

  // 1분마다 지표 API 폴링
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const res = await fetch("/api/market-indices");
        if (!res.ok) return;
        const data: MarketIndices = await res.json();
        animateTo(data);
      } catch {
        // 네트워크 에러 무시, 다음 폴링에서 재시도
      }
    }, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [animateTo]);

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
