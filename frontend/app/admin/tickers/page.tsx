"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { TickerDictionary } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  ArrowLeft,
  Check,
  Edit2,
  Search,
  Trash2,
  BookOpen,
} from "lucide-react";



type StatusFilter = "ALL" | "PENDING" | "ACTIVE" | "INACTIVE";
type MarketFilter = "ALL" | "KR" | "US";

const STATUS_CONFIG: Record<
  string,
  { label: string; color: string; bg: string }
> = {
  PENDING: {
    label: "임시",
    color: "text-amber-700 dark:text-amber-400",
    bg: "bg-amber-50 border-amber-200 dark:bg-amber-900/20 dark:border-amber-800",
  },
  ACTIVE: {
    label: "등록",
    color: "text-emerald-700 dark:text-emerald-400",
    bg: "bg-emerald-50 border-emerald-200 dark:bg-emerald-900/20 dark:border-emerald-800",
  },
  INACTIVE: {
    label: "비활성",
    color: "text-slate-500 dark:text-slate-500",
    bg: "bg-slate-50 border-slate-200 dark:bg-slate-800/50 dark:border-slate-700",
  },
};

export default function TickerDictionaryPage() {
  const [tickers, setTickers] = useState<TickerDictionary[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [marketFilter, setMarketFilter] = useState<MarketFilter>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const [editItem, setEditItem] = useState<TickerDictionary | null>(null);
  const [editForm, setEditForm] = useState({
    company_name: "",
    ticker_symbol: "",
    market: "KR" as string,
    status: "PENDING" as string,
  });
  const [editError, setEditError] = useState<string | null>(null);
  const [editSaving, setEditSaving] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<TickerDictionary | null>(
    null
  );

  const fetchTickers = useCallback(async () => {
    setLoading(true);
    try {
      const qp = new URLSearchParams();
      if (statusFilter !== "ALL") qp.set("status", statusFilter);
      if (marketFilter !== "ALL") qp.set("market", marketFilter);
      const params = qp.toString() ? `?${qp.toString()}` : "";
      const res = await fetch(`/api/ticker-dictionary${params}`);
      if (res.ok) {
        setTickers(await res.json());
      }
    } catch (e) {
      console.error("Failed to fetch tickers:", e);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, marketFilter]);

  useEffect(() => {
    fetchTickers();
  }, [fetchTickers]);

  const handleEdit = (item: TickerDictionary) => {
    setEditItem(item);
    setEditForm({
      company_name: item.company_name,
      ticker_symbol: item.ticker_symbol,
      market: item.market,
      status: item.status,
    });
    setEditError(null);
  };

  const hasEditChanges = !!editItem && (
    editForm.company_name.trim() !== editItem.company_name ||
    editForm.ticker_symbol.trim() !== editItem.ticker_symbol ||
    editForm.market !== editItem.market ||
    editForm.status !== editItem.status
  );
  const canSaveEdit =
    hasEditChanges &&
    editForm.company_name.trim().length > 0 &&
    editForm.ticker_symbol.trim().length > 0;

  const handleSave = async () => {
    if (!editItem || !canSaveEdit) return;
    setEditSaving(true);
    setEditError(null);
    try {
      const res = await fetch(
        `/api/ticker-dictionary/${editItem.id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            company_name: editForm.company_name.trim(),
            ticker_symbol: editForm.ticker_symbol.trim(),
            market: editForm.market,
            status: editForm.status,
          }),
        }
      );
      if (res.ok) {
        setEditItem(null);
        fetchTickers();
      } else {
        const data = await res.json().catch(() => null);
        setEditError(
          data?.detail ||
            data?.error ||
            (res.status === 409
              ? "이미 등록된 기업명입니다."
              : "수정에 실패했습니다.")
        );
      }
    } catch (e) {
      console.error("Failed to update ticker:", e);
      setEditError("서버에 연결할 수 없습니다.");
    } finally {
      setEditSaving(false);
    }
  };

  const handleRegister = async (item: TickerDictionary) => {
    try {
      const res = await fetch(
        `/api/ticker-dictionary/${item.id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            company_name: item.company_name,
            ticker_symbol: item.ticker_symbol,
            market: item.market,
            status: "ACTIVE",
          }),
        }
      );
      if (res.ok) fetchTickers();
    } catch (e) {
      console.error("Failed to register ticker:", e);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      const res = await fetch(
        `/api/ticker-dictionary/${deleteTarget.id}`,
        { method: "DELETE" }
      );
      if (res.ok) {
        setDeleteTarget(null);
        fetchTickers();
      }
    } catch (e) {
      console.error("Failed to delete ticker:", e);
    }
  };

  const filtered = tickers.filter((t) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      t.company_name.toLowerCase().includes(q) ||
      t.ticker_symbol.toLowerCase().includes(q)
    );
  });

  const counts = {
    ALL: tickers.length,
    PENDING: tickers.filter((t) => t.status === "PENDING").length,
    ACTIVE: tickers.filter((t) => t.status === "ACTIVE").length,
    INACTIVE: tickers.filter((t) => t.status === "INACTIVE").length,
  };

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950 p-4 sm:p-8">
      <div className="mx-auto max-w-5xl space-y-6">
        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/">
              <Button variant="ghost" size="icon-sm">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </Link>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
                <BookOpen className="w-6 h-6 text-indigo-500" />
                티커 사전 관리
              </h1>
              <p className="text-sm text-slate-500 mt-0.5">
                AI가 자동 수집한 티커를 검수하고 등록합니다
              </p>
            </div>
          </div>
        </div>

        {/* 필터 + 검색 */}
        <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
          <div className="flex gap-3 flex-wrap items-center">
            <div className="flex gap-2 flex-wrap">
              {(["ALL", "PENDING", "ACTIVE", "INACTIVE"] as StatusFilter[]).map(
                (s) => (
                  <button
                    key={s}
                    onClick={() => setStatusFilter(s)}
                    className={`px-4 py-2 rounded-full text-xs font-bold transition-all ${
                      statusFilter === s
                        ? s === "ALL"
                          ? "bg-slate-800 text-white dark:bg-slate-100 dark:text-slate-900 shadow-md"
                          : s === "PENDING"
                            ? "bg-amber-500 text-white shadow-md"
                            : s === "ACTIVE"
                              ? "bg-emerald-500 text-white shadow-md"
                              : "bg-slate-500 text-white shadow-md"
                        : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400"
                    }`}
                  >
                    {s === "ALL"
                      ? "전체"
                      : STATUS_CONFIG[s].label}
                    {statusFilter === s && ` (${counts[s]})`}
                  </button>
                )
              )}
            </div>

            <div className="w-px h-6 bg-slate-200 dark:bg-slate-700 hidden sm:block" />

            <div className="flex gap-2">
              {(["ALL", "KR", "US"] as MarketFilter[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMarketFilter(m)}
                  className={`px-3 py-2 rounded-full text-xs font-bold transition-all ${
                    marketFilter === m
                      ? "bg-indigo-500 text-white shadow-md"
                      : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400"
                  }`}
                >
                  {m === "ALL" ? "전체 시장" : m === "KR" ? "🇰🇷 한국" : "🇺🇸 미국"}
                </button>
              ))}
            </div>
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="기업명 또는 티커 검색..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>
        </div>

        {/* 테이블 */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-slate-400">
              불러오는 중...
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-12 text-center text-slate-400">
              {searchQuery
                ? "검색 결과가 없습니다."
                : "등록된 티커가 없습니다."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
                    <th className="text-left p-4 font-semibold text-slate-600 dark:text-slate-400">
                      기업명
                    </th>
                    <th className="text-left p-4 font-semibold text-slate-600 dark:text-slate-400">
                      티커
                    </th>
                    <th className="text-center p-4 font-semibold text-slate-600 dark:text-slate-400">
                      시장
                    </th>
                    <th className="text-center p-4 font-semibold text-slate-600 dark:text-slate-400">
                      상태
                    </th>
                    <th className="text-center p-4 font-semibold text-slate-600 dark:text-slate-400">
                      수정일
                    </th>
                    <th className="text-center p-4 font-semibold text-slate-600 dark:text-slate-400">
                      액션
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => {
                    const cfg = STATUS_CONFIG[item.status] || STATUS_CONFIG.PENDING;
                    return (
                      <tr
                        key={item.id}
                        className="border-b border-slate-50 dark:border-slate-800/50 hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors"
                      >
                        <td className="p-4 font-medium text-slate-900 dark:text-slate-100">
                          {item.company_name}
                        </td>
                        <td className="p-4">
                          <code className="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded font-mono text-slate-700 dark:text-slate-300">
                            {item.ticker_symbol}
                          </code>
                        </td>
                        <td className="p-4 text-center">
                          <span className="text-xs font-medium">
                            {item.market === "KR" ? "🇰🇷" : item.market === "US" ? "🇺🇸" : item.market}
                          </span>
                        </td>
                        <td className="p-4 text-center">
                          <Badge
                            variant="outline"
                            className={`text-xs ${cfg.color} ${cfg.bg}`}
                          >
                            {cfg.label}
                          </Badge>
                        </td>
                        <td className="p-4 text-center text-xs text-slate-400">
                          {item.updated_at
                            ? new Date(item.updated_at).toLocaleDateString(
                                "ko-KR"
                              )
                            : "-"}
                        </td>
                        <td className="p-4">
                          <div className="flex items-center justify-center gap-1">
                            {item.status === "PENDING" && (
                              <Button
                                size="xs"
                                variant="ghost"
                                className="text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 dark:hover:bg-emerald-900/20"
                                onClick={() => handleRegister(item)}
                                title="등록"
                              >
                                <Check className="w-3.5 h-3.5" />
                              </Button>
                            )}
                            <Button
                              size="xs"
                              variant="ghost"
                              className="text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20"
                              onClick={() => handleEdit(item)}
                              title="수정"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              size="xs"
                              variant="ghost"
                              className="text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                              onClick={() => setDeleteTarget(item)}
                              title="삭제"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* 수정 다이얼로그 */}
        <Dialog
          open={!!editItem}
          onOpenChange={(open) => !open && setEditItem(null)}
        >
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>티커 정보 수정</DialogTitle>
              <DialogDescription>
                기업명, 티커 심볼, 상태를 수정할 수 있습니다.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  기업명
                </label>
                <input
                  type="text"
                  value={editForm.company_name}
                  onChange={(e) => {
                    setEditForm((f) => ({
                      ...f,
                      company_name: e.target.value,
                    }));
                    setEditError(null);
                  }}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  티커 심볼
                </label>
                <input
                  type="text"
                  value={editForm.ticker_symbol}
                  onChange={(e) => {
                    setEditForm((f) => ({
                      ...f,
                      ticker_symbol: e.target.value,
                    }));
                    setEditError(null);
                  }}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 font-mono"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  시장
                </label>
                <div className="flex gap-2">
                  {(["KR", "US"] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() =>
                        setEditForm((f) => ({ ...f, market: m }))
                      }
                      className={`flex-1 px-3 py-2 rounded-lg text-xs font-bold border transition-all ${
                        editForm.market === m
                          ? "bg-slate-800 text-white border-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:border-slate-100"
                          : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"
                      }`}
                    >
                      {m === "KR" ? "🇰🇷 한국" : "🇺🇸 미국"}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  상태
                </label>
                <div className="flex gap-2">
                  {(["PENDING", "ACTIVE", "INACTIVE"] as const).map((s) => {
                    const cfg = STATUS_CONFIG[s];
                    return (
                      <button
                        key={s}
                        onClick={() =>
                          setEditForm((f) => ({ ...f, status: s }))
                        }
                        className={`flex-1 px-3 py-2 rounded-lg text-xs font-bold border transition-all ${
                          editForm.status === s
                            ? s === "PENDING"
                              ? "bg-amber-500 text-white border-amber-500"
                              : s === "ACTIVE"
                                ? "bg-emerald-500 text-white border-emerald-500"
                                : "bg-slate-500 text-white border-slate-500"
                            : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"
                        }`}
                      >
                        {cfg.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
            {editError && (
              <p className="text-sm font-medium text-red-600 dark:text-red-400 -mt-1">
                {editError}
              </p>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditItem(null)}>
                취소
              </Button>
              <Button
                onClick={handleSave}
                disabled={!canSaveEdit || editSaving}
              >
                {editSaving ? "저장 중..." : "저장"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* 삭제 확인 다이얼로그 */}
        <Dialog
          open={!!deleteTarget}
          onOpenChange={(open) => !open && setDeleteTarget(null)}
        >
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>티커 삭제 확인</DialogTitle>
              <DialogDescription>
                <strong>{deleteTarget?.company_name}</strong> (
                {deleteTarget?.ticker_symbol})을(를) 삭제하시겠습니까? 이 작업은
                되돌릴 수 없습니다.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setDeleteTarget(null)}
              >
                취소
              </Button>
              <Button
                variant="destructive"
                onClick={handleDelete}
              >
                삭제
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </main>
  );
}
