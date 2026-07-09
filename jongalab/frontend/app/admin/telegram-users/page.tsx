"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { TelegramUser } from "@/types";
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
  Search,
  Send,
  Trash2,
} from "lucide-react";

type RoleFilter = "ALL" | "ADMIN" | "NORMAL";
type ActiveFilter = "ALL" | "ACTIVE" | "INACTIVE";

const ROLE_LABEL: Record<string, string> = {
  ADMIN: "관리자",
  NORMAL: "일반",
};

const EMPTY_FORM = {
  id: "",
  name: "",
  role: "NORMAL" as "ADMIN" | "NORMAL",
  is_active: true,
};

export default function TelegramUserManagementPage() {
  const [users, setUsers] = useState<TelegramUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("ALL");
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const [editItem, setEditItem] = useState<TelegramUser | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [formError, setFormError] = useState<string | null>(null);
  const [formSaving, setFormSaving] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<TelegramUser | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const qp = new URLSearchParams();
      if (roleFilter !== "ALL") qp.set("role", roleFilter);
      if (activeFilter !== "ALL")
        qp.set("is_active", activeFilter === "ACTIVE" ? "true" : "false");
      const params = qp.toString() ? `?${qp.toString()}` : "";
      const res = await fetch(`/api/telegram-users${params}`);
      if (res.ok) {
        setUsers(await res.json());
      }
    } catch (e) {
      console.error("Failed to fetch telegram users:", e);
    } finally {
      setLoading(false);
    }
  }, [roleFilter, activeFilter]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const openCreate = () => {
    setForm({ ...EMPTY_FORM });
    setFormError(null);
    setCreateOpen(true);
  };

  const openEdit = (item: TelegramUser) => {
    setEditItem(item);
    setForm({
      id: item.id,
      name: item.name,
      role: item.role,
      is_active: item.is_active,
    });
    setFormError(null);
  };

  const hasFormChanges = !editItem || (
    form.name.trim() !== editItem.name ||
    form.role !== editItem.role ||
    form.is_active !== editItem.is_active
  );
  const canSubmit =
    (editItem ? true : form.id.trim().length > 0) &&
    form.name.trim().length > 0 &&
    hasFormChanges;

  const submitForm = async () => {
    if (!canSubmit) return;
    const payload = editItem
      ? {
          name: form.name.trim(),
          role: form.role,
          is_active: form.is_active,
        }
      : {
          id: form.id.trim(),
          name: form.name.trim(),
          role: form.role,
          is_active: form.is_active,
        };
    const url = editItem
      ? `/api/telegram-users/${editItem.id}`
      : `/api/telegram-users`;
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
        fetchUsers();
      } else {
        const data = await res.json().catch(() => null);
        setFormError(
          data?.detail ||
            data?.error ||
            (res.status === 409
              ? "이미 등록된 chat id입니다."
              : editItem
                ? "수정에 실패했습니다."
                : "생성에 실패했습니다.")
        );
      }
    } catch (e) {
      console.error("Failed to submit telegram user:", e);
      setFormError("서버에 연결할 수 없습니다.");
    } finally {
      setFormSaving(false);
    }
  };

  const handleToggleActive = async (item: TelegramUser) => {
    try {
      const res = await fetch(`/api/telegram-users/${item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: item.name,
          role: item.role,
          is_active: !item.is_active,
        }),
      });
      if (res.ok) fetchUsers();
    } catch (e) {
      console.error("Failed to toggle telegram user:", e);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      const res = await fetch(`/api/telegram-users/${deleteTarget.id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setDeleteTarget(null);
        fetchUsers();
      }
    } catch (e) {
      console.error("Failed to delete telegram user:", e);
    }
  };

  const filtered = users.filter((u) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      u.id.toLowerCase().includes(q) ||
      u.name.toLowerCase().includes(q) ||
      u.role.toLowerCase().includes(q)
    );
  });

  const counts = {
    ALL: users.length,
    ADMIN: users.filter((u) => u.role === "ADMIN").length,
    NORMAL: users.filter((u) => u.role === "NORMAL").length,
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
                <Send className="w-6 h-6 text-indigo-500" />
                텔레그램 유저 관리
              </h1>
              <p className="text-sm text-slate-500 mt-0.5">
                알림 전송 대상 텔레그램 유저와 역할(ADMIN/NORMAL)을 관리합니다
              </p>
            </div>
          </div>
          <Button onClick={openCreate} className="gap-1.5">
            <Plus className="w-4 h-4" />
            새 유저
          </Button>
        </div>

        {/* 필터 + 검색 */}
        <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
          <div className="flex gap-3 flex-wrap items-center">
            <div className="flex gap-2 flex-wrap">
              {(["ALL", "ADMIN", "NORMAL"] as RoleFilter[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setRoleFilter(r)}
                  className={`px-4 py-2 rounded-full text-xs font-bold transition-all ${
                    roleFilter === r
                      ? r === "ALL"
                        ? "bg-slate-800 text-white dark:bg-slate-100 dark:text-slate-900 shadow-md"
                        : r === "ADMIN"
                          ? "bg-amber-500 text-white shadow-md"
                          : "bg-indigo-500 text-white shadow-md"
                      : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400"
                  }`}
                >
                  {r === "ALL" ? "전체" : ROLE_LABEL[r] ?? r}
                  {roleFilter === r && ` (${counts[r]})`}
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
              placeholder="이름, chat id, 역할 검색..."
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
                : "등록된 유저가 없습니다."}
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
                      Chat ID
                    </th>
                    <th className="text-center p-4 font-semibold text-slate-600 dark:text-slate-400">
                      역할
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
                        {item.name}
                      </td>
                      <td className="p-4">
                        <code className="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded font-mono text-slate-700 dark:text-slate-300">
                          {item.id}
                        </code>
                      </td>
                      <td className="p-4 text-center">
                        <Badge
                          variant="outline"
                          className={`text-xs ${
                            item.role === "ADMIN"
                              ? "text-amber-700 dark:text-amber-400 bg-amber-50 border-amber-200 dark:bg-amber-900/20 dark:border-amber-800"
                              : "text-indigo-700 dark:text-indigo-400 bg-indigo-50 border-indigo-200 dark:bg-indigo-900/20 dark:border-indigo-800"
                          }`}
                        >
                          {ROLE_LABEL[item.role] ?? item.role}
                        </Badge>
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
                {editItem ? "텔레그램 유저 수정" : "새 텔레그램 유저 추가"}
              </DialogTitle>
              <DialogDescription>
                텔레그램 chat id, 이름, 역할, 활성 여부를 설정할 수 있습니다.
                ADMIN 유저만 갭 체크 알림을 수신합니다.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  Chat ID {editItem && <span className="text-xs text-slate-400">(수정 불가)</span>}
                </label>
                <input
                  type="text"
                  value={form.id}
                  disabled={!!editItem}
                  onChange={(e) => {
                    setForm((f) => ({ ...f, id: e.target.value }));
                    setFormError(null);
                  }}
                  placeholder="7824283455"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 font-mono disabled:opacity-60 disabled:cursor-not-allowed"
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
                  placeholder="CHAT_ID"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  역할
                </label>
                <div className="flex gap-2">
                  {(["ADMIN", "NORMAL"] as const).map((r) => (
                    <button
                      key={r}
                      onClick={() => setForm((f) => ({ ...f, role: r }))}
                      className={`flex-1 px-3 py-2 rounded-lg text-xs font-bold border transition-all ${
                        form.role === r
                          ? r === "ADMIN"
                            ? "bg-amber-500 text-white border-amber-500"
                            : "bg-indigo-500 text-white border-indigo-500"
                          : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"
                      }`}
                    >
                      {ROLE_LABEL[r]}
                    </button>
                  ))}
                </div>
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
              <DialogTitle>텔레그램 유저 삭제 확인</DialogTitle>
              <DialogDescription>
                <strong>{deleteTarget?.name}</strong>
                (을)를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
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
