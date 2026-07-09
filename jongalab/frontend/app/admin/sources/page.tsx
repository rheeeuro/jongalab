"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Source } from "@/types";
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
  Edit2,
  Plus,
  Rss,
  Search,
  Trash2,
} from "lucide-react";

type PlatformFilter = "ALL" | "youtube" | "telegram";
type ActiveFilter = "ALL" | "ACTIVE" | "INACTIVE";

const PLATFORM_LABEL: Record<string, string> = {
  youtube: "유튜브",
  telegram: "텔레그램",
};

const EMPTY_FORM = {
  platform: "youtube",
  identifier: "",
  name: "",
  is_active: true,
};

export default function SourceManagementPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [platformFilter, setPlatformFilter] = useState<PlatformFilter>("ALL");
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const [editItem, setEditItem] = useState<Source | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [formError, setFormError] = useState<string | null>(null);
  const [formSaving, setFormSaving] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<Source | null>(null);

  const fetchSources = useCallback(async () => {
    setLoading(true);
    try {
      const qp = new URLSearchParams();
      if (platformFilter !== "ALL") qp.set("platform", platformFilter);
      if (activeFilter !== "ALL")
        qp.set("is_active", activeFilter === "ACTIVE" ? "true" : "false");
      const params = qp.toString() ? `?${qp.toString()}` : "";
      const res = await fetch(`/api/sources${params}`);
      if (res.ok) {
        setSources(await res.json());
      }
    } catch (e) {
      console.error("Failed to fetch sources:", e);
    } finally {
      setLoading(false);
    }
  }, [platformFilter, activeFilter]);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  const openCreate = () => {
    setForm({ ...EMPTY_FORM });
    setFormError(null);
    setCreateOpen(true);
  };

  const openEdit = (item: Source) => {
    setEditItem(item);
    setForm({
      platform: item.platform,
      identifier: item.identifier,
      name: item.name ?? "",
      is_active: item.is_active,
    });
    setFormError(null);
  };

  const hasFormChanges = !editItem || (
    form.platform.trim() !== editItem.platform ||
    form.identifier.trim() !== editItem.identifier ||
    (form.name.trim() || null) !== (editItem.name ?? null) ||
    form.is_active !== editItem.is_active
  );
  const canSubmit =
    form.platform.trim().length > 0 &&
    form.identifier.trim().length > 0 &&
    hasFormChanges;

  const submitForm = async () => {
    if (!canSubmit) return;
    const payload = {
      platform: form.platform.trim(),
      identifier: form.identifier.trim(),
      name: form.name.trim() || null,
      is_active: form.is_active,
    };
    const url = editItem ? `/api/sources/${editItem.id}` : `/api/sources`;
    const method = editItem ? "PUT" : "POST";

    setFormSaving(true);
    setFormError(null);
    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setCreateOpen(false);
        setEditItem(null);
        fetchSources();
      } else {
        const data = await res.json().catch(() => null);
        setFormError(
          data?.detail ||
            data?.error ||
            (res.status === 409
              ? "이미 등록된 식별자입니다."
              : editItem
                ? "수정에 실패했습니다."
                : "생성에 실패했습니다.")
        );
      }
    } catch (e) {
      console.error("Failed to submit source:", e);
      setFormError("서버에 연결할 수 없습니다.");
    } finally {
      setFormSaving(false);
    }
  };

  const handleToggleActive = async (item: Source) => {
    try {
      const res = await fetch(`/api/sources/${item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: item.platform,
          identifier: item.identifier,
          name: item.name,
          is_active: !item.is_active,
        }),
      });
      if (res.ok) fetchSources();
    } catch (e) {
      console.error("Failed to toggle source:", e);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      const res = await fetch(`/api/sources/${deleteTarget.id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setDeleteTarget(null);
        fetchSources();
      }
    } catch (e) {
      console.error("Failed to delete source:", e);
    }
  };

  const filtered = sources.filter((s) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      s.identifier.toLowerCase().includes(q) ||
      (s.name ?? "").toLowerCase().includes(q) ||
      s.platform.toLowerCase().includes(q)
    );
  });

  const counts = {
    ALL: sources.length,
    youtube: sources.filter((s) => s.platform === "youtube").length,
    telegram: sources.filter((s) => s.platform === "telegram").length,
  };

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
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
                <Rss className="w-6 h-6 text-indigo-500" />
                소스 관리
              </h1>
              <p className="text-sm text-slate-500 mt-0.5">
                수집 대상 유튜브·텔레그램 채널을 관리합니다
              </p>
            </div>
          </div>
          <Button onClick={openCreate} className="gap-1.5">
            <Plus className="w-4 h-4" />
            새 소스
          </Button>
        </div>

        {/* 필터 + 검색 */}
        <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
          <div className="flex gap-3 flex-wrap items-center">
            <div className="flex gap-2 flex-wrap">
              {(["ALL", "youtube", "telegram"] as PlatformFilter[]).map((p) => (
                <button
                  key={p}
                  onClick={() => setPlatformFilter(p)}
                  className={`px-4 py-2 rounded-full text-xs font-bold transition-all ${
                    platformFilter === p
                      ? p === "ALL"
                        ? "bg-slate-800 text-white dark:bg-slate-100 dark:text-slate-900 shadow-md"
                        : "bg-indigo-500 text-white shadow-md"
                      : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400"
                  }`}
                >
                  {p === "ALL" ? "전체" : PLATFORM_LABEL[p] ?? p}
                  {platformFilter === p && ` (${counts[p]})`}
                </button>
              ))}
            </div>

            <div className="w-px h-6 bg-slate-200 dark:bg-slate-700 hidden sm:block" />

            <div className="flex gap-2">
              {(["ALL", "ACTIVE", "INACTIVE"] as ActiveFilter[]).map((a) => (
                <button
                  key={a}
                  onClick={() => setActiveFilter(a)}
                  className={`px-3 py-2 rounded-full text-xs font-bold transition-all ${
                    activeFilter === a
                      ? a === "ACTIVE"
                        ? "bg-emerald-500 text-white shadow-md"
                        : a === "INACTIVE"
                          ? "bg-slate-500 text-white shadow-md"
                          : "bg-slate-800 text-white dark:bg-slate-100 dark:text-slate-900 shadow-md"
                      : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400"
                  }`}
                >
                  {a === "ALL"
                    ? "전체 상태"
                    : a === "ACTIVE"
                      ? "활성"
                      : "비활성"}
                </button>
              ))}
            </div>
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="이름, 식별자, 플랫폼 검색..."
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
                : "등록된 소스가 없습니다."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
                    <th className="text-left p-4 font-semibold text-slate-600 dark:text-slate-400">
                      이름
                    </th>
                    <th className="text-left p-4 font-semibold text-slate-600 dark:text-slate-400">
                      식별자
                    </th>
                    <th className="text-center p-4 font-semibold text-slate-600 dark:text-slate-400">
                      플랫폼
                    </th>
                    <th className="text-center p-4 font-semibold text-slate-600 dark:text-slate-400">
                      상태
                    </th>
                    <th className="text-center p-4 font-semibold text-slate-600 dark:text-slate-400">
                      등록일
                    </th>
                    <th className="text-center p-4 font-semibold text-slate-600 dark:text-slate-400">
                      액션
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => (
                    <tr
                      key={item.id}
                      className="border-b border-slate-50 dark:border-slate-800/50 hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors"
                    >
                      <td className="p-4 font-medium text-slate-900 dark:text-slate-100">
                        {item.name || (
                          <span className="text-slate-400">-</span>
                        )}
                      </td>
                      <td className="p-4">
                        <code className="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded font-mono text-slate-700 dark:text-slate-300">
                          {item.identifier}
                        </code>
                      </td>
                      <td className="p-4 text-center">
                        <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                          {PLATFORM_LABEL[item.platform] ?? item.platform}
                        </span>
                      </td>
                      <td className="p-4 text-center">
                        <button
                          onClick={() => handleToggleActive(item)}
                          title="클릭해서 토글"
                        >
                          <Badge
                            variant="outline"
                            className={`text-xs cursor-pointer ${
                              item.is_active
                                ? "text-emerald-700 dark:text-emerald-400 bg-emerald-50 border-emerald-200 dark:bg-emerald-900/20 dark:border-emerald-800"
                                : "text-slate-500 dark:text-slate-500 bg-slate-50 border-slate-200 dark:bg-slate-800/50 dark:border-slate-700"
                            }`}
                          >
                            {item.is_active ? "활성" : "비활성"}
                          </Badge>
                        </button>
                      </td>
                      <td className="p-4 text-center text-xs text-slate-400">
                        {item.created_at
                          ? new Date(item.created_at).toLocaleDateString(
                              "ko-KR"
                            )
                          : "-"}
                      </td>
                      <td className="p-4">
                        <div className="flex items-center justify-center gap-1">
                          <Button
                            size="xs"
                            variant="ghost"
                            className="text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20"
                            onClick={() => openEdit(item)}
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
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* 생성/수정 다이얼로그 */}
        <Dialog
          open={createOpen || !!editItem}
          onOpenChange={(open) => {
            if (!open) {
              setCreateOpen(false);
              setEditItem(null);
            }
          }}
        >
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>
                {editItem ? "소스 정보 수정" : "새 소스 추가"}
              </DialogTitle>
              <DialogDescription>
                플랫폼, 식별자, 이름, 활성 여부를 설정할 수 있습니다.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  플랫폼
                </label>
                <div className="flex gap-2">
                  {(["youtube", "telegram"] as const).map((p) => (
                    <button
                      key={p}
                      onClick={() => {
                        setForm((f) => ({ ...f, platform: p }));
                        setFormError(null);
                      }}
                      className={`flex-1 px-3 py-2 rounded-lg text-xs font-bold border transition-all ${
                        form.platform === p
                          ? "bg-slate-800 text-white border-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:border-slate-100"
                          : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"
                      }`}
                    >
                      {PLATFORM_LABEL[p]}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  value={form.platform}
                  onChange={(e) => {
                    setForm((f) => ({ ...f, platform: e.target.value }));
                    setFormError(null);
                  }}
                  placeholder="custom platform"
                  className="mt-2 w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 font-mono"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  식별자 (channel id / username)
                </label>
                <input
                  type="text"
                  value={form.identifier}
                  onChange={(e) => {
                    setForm((f) => ({ ...f, identifier: e.target.value }));
                    setFormError(null);
                  }}
                  placeholder="UCxxxxxx 또는 @channel"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 font-mono"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  이름 (표시용)
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, name: e.target.value }))
                  }
                  placeholder="슈카월드"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  활성 여부
                </label>
                <div className="flex gap-2">
                  {([true, false] as const).map((v) => (
                    <button
                      key={String(v)}
                      onClick={() =>
                        setForm((f) => ({ ...f, is_active: v }))
                      }
                      className={`flex-1 px-3 py-2 rounded-lg text-xs font-bold border transition-all ${
                        form.is_active === v
                          ? v
                            ? "bg-emerald-500 text-white border-emerald-500"
                            : "bg-slate-500 text-white border-slate-500"
                          : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"
                      }`}
                    >
                      {v ? "활성" : "비활성"}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            {formError && (
              <p className="text-sm font-medium text-red-600 dark:text-red-400 -mt-1">
                {formError}
              </p>
            )}
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setCreateOpen(false);
                  setEditItem(null);
                }}
              >
                취소
              </Button>
              <Button onClick={submitForm} disabled={!canSubmit || formSaving}>
                {formSaving ? (editItem ? "저장 중..." : "추가 중...") : (editItem ? "저장" : "추가")}
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
              <DialogTitle>소스 삭제 확인</DialogTitle>
              <DialogDescription>
                <strong>{deleteTarget?.name || deleteTarget?.identifier}</strong>
                을(를) 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setDeleteTarget(null)}
              >
                취소
              </Button>
              <Button variant="destructive" onClick={handleDelete}>
                삭제
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </main>
  );
}
