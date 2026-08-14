import { MetadataRoute } from "next";
import { API_BASE } from "@/lib/api";
import { StockReport } from "@/types";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://jongalab.com";
const REVALIDATE_SECONDS = 3600;

function parseLastModified(date?: string) {
  if (!date) return new Date();

  const parsedDate = new Date(date);
  return Number.isNaN(parsedDate.getTime()) ? new Date() : parsedDate;
}

async function fetchJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      next: { revalidate: REVALIDATE_SECONDS },
    });

    if (!res.ok) return fallback;

    return res.json();
  } catch (error) {
    console.error(`사이트맵 데이터 조회 실패 (${path}):`, error);
    return fallback;
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const baseUrl = SITE_URL.replace(/\/$/, "");
  const now = new Date();

  // 검색 노출 대상이 되는 고정 공개 페이지
  const routes: MetadataRoute.Sitemap = [
    {
      url: baseUrl,
      lastModified: now,
      changeFrequency: "always",
      priority: 1.0,
    },
    {
      url: `${baseUrl}/market`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${baseUrl}/news`,
      lastModified: now,
      changeFrequency: "hourly",
      priority: 0.8,
    },
    // 추천 성적(달력·누적 승률) — 추천 화면 다음으로 신뢰에 직접 닿는 공개 화면
    {
      url: `${baseUrl}/record`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${baseUrl}/lab`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.7,
    },
  ];

  const reportDates = await fetchJson<string[]>(
    "/api/stock-report/dates?limit=100",
    []
  );

  const uniqueDates = Array.from(new Set(reportDates));

  const reportRoutes: MetadataRoute.Sitemap = uniqueDates.map((date) => ({
    url: `${baseUrl}/reports/${encodeURIComponent(date)}`,
    lastModified: parseLastModified(date),
    changeFrequency: "never",
    priority: 0.8,
  }));

  routes.push(...reportRoutes);

  // 날짜별 종목 리포트 상세 페이지 (당일은 갭 데이터 미확정 → 카드 페이지 fetch 캐시 오염 방지로 제외)
  const todaySeoul = new Date().toLocaleDateString("en-CA", {
    timeZone: "Asia/Seoul",
  });
  const stockReportsByDate = await Promise.all(
    uniqueDates
      .filter((date) => date < todaySeoul)
      .map((date) =>
        fetchJson<StockReport[]>(`/api/stock-report/${encodeURIComponent(date)}`, [])
      )
  );

  const stockReportRoutes: MetadataRoute.Sitemap = stockReportsByDate
    .flat()
    .map((report) => ({
      url: `${baseUrl}/reports/${encodeURIComponent(
        report.report_date
      )}/${encodeURIComponent(report.stock_code)}`,
      lastModified: parseLastModified(report.created_at ?? report.report_date),
      changeFrequency: "never",
      priority: 0.7,
    }));

  routes.push(...stockReportRoutes);

  // 종목 상시 페이지는 **리포트 이력이 있는 종목만** 싣는다. 티커 사전 전체를 실으면
  // 대부분이 "수집된 데이터 없음" 화면이라 색인되지 않고 크롤 예산만 쓴다.
  // 근거: docs/plan/seo/search-visibility.md
  const latestReportByStock = new Map<string, string>();
  for (const report of stockReportsByDate.flat()) {
    const prev = latestReportByStock.get(report.stock_code);
    if (!prev || report.report_date > prev) {
      latestReportByStock.set(report.stock_code, report.report_date);
    }
  }

  const stockRoutes: MetadataRoute.Sitemap = Array.from(
    latestReportByStock,
    ([stockCode, latestDate]) => ({
      url: `${baseUrl}/stocks/${encodeURIComponent(stockCode)}`,
      lastModified: parseLastModified(latestDate),
      changeFrequency: "daily" as const,
      priority: 0.7,
    })
  );

  routes.push(...stockRoutes);

  return routes;
}
