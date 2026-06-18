import { MetadataRoute } from "next";
import { API_BASE } from "@/lib/api";
import { DailySummary, StockReport, TickerDictionary } from "@/types";

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
  ];

  const reports = await fetchJson<DailySummary[]>(
    "/api/daily-summary-list?limit=100",
    []
  );

  const reportMap = new Map<string, DailySummary>();
  reports.forEach((report) => {
    if (!reportMap.has(report.report_date)) {
      reportMap.set(report.report_date, report);
    }
  });

  const reportRoutes: MetadataRoute.Sitemap = Array.from(reportMap.values()).map(
    (report) => ({
      url: `${baseUrl}/reports/${encodeURIComponent(report.report_date)}`,
      lastModified: parseLastModified(report.created_at ?? report.report_date),
      changeFrequency: "never",
      priority: 0.8,
    })
  );

  routes.push(...reportRoutes);

  // 날짜별 종목 리포트 상세 페이지 (당일은 갭 데이터 미확정 → 카드 페이지 fetch 캐시 오염 방지로 제외)
  const todaySeoul = new Date().toLocaleDateString("en-CA", {
    timeZone: "Asia/Seoul",
  });
  const stockReportsByDate = await Promise.all(
    Array.from(reportMap.keys())
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

  const tickers = await fetchJson<TickerDictionary[]>(
    "/api/ticker-dictionary?status=ACTIVE",
    []
  );

  const stockRoutes: MetadataRoute.Sitemap = tickers.map((ticker) => ({
    url: `${baseUrl}/stocks/${encodeURIComponent(ticker.ticker_symbol)}`,
    lastModified: parseLastModified(ticker.updated_at),
    changeFrequency: "daily",
    priority: 0.7,
  }));

  routes.push(...stockRoutes);

  return routes;
}
