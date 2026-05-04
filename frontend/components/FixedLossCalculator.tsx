"use client";

import { useEffect, useState } from "react";
import { Calculator } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const LS_KEY_STOP_LOSS_PCT = "fixedLossCalc_stopLossPct";
const LS_KEY_FIXED_LOSS = "fixedLossCalc_fixedLoss";

export function FixedLossCalculator({ ticker }: { ticker: string }) {
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState("");
  const [stopLossPct, setStopLossPct] = useState(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem(LS_KEY_STOP_LOSS_PCT) ?? "";
  });
  const [fixedLoss, setFixedLoss] = useState(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem(LS_KEY_FIXED_LOSS) ?? "";
  });
  const [priceLoaded, setPriceLoaded] = useState(false);

  // 모달 열릴 때 실시간 가격 조회
  useEffect(() => {
    if (!open || priceLoaded) return;
    fetch(`/api/stock-price/${ticker}`)
      .then((res) => res.json())
      .then((json) => {
        if (!json.error && json.price) {
          setPrice(String(json.price));
        }
        setPriceLoaded(true);
      })
      .catch(() => setPriceLoaded(true));
  }, [open, ticker, priceLoaded]);

  // localStorage 저장
  useEffect(() => {
    if (stopLossPct) localStorage.setItem(LS_KEY_STOP_LOSS_PCT, stopLossPct);
  }, [stopLossPct]);

  useEffect(() => {
    if (fixedLoss) localStorage.setItem(LS_KEY_FIXED_LOSS, fixedLoss);
  }, [fixedLoss]);

  const priceNum = parseFloat(price);
  const pctNum = parseFloat(stopLossPct);
  const lossNum = parseFloat(fixedLoss);

  const isValid = priceNum > 0 && pctNum > 0 && lossNum > 0;
  const lossPerShare = isValid ? priceNum * (pctNum / 100) : 0;
  const shares = isValid ? Math.floor(lossNum / lossPerShare) : 0;
  const totalCost = isValid ? shares * priceNum : 0;
  const actualLoss = isValid ? shares * lossPerShare : 0;

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) setPriceLoaded(false);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
        >
          <Calculator className="w-4 h-4" />
          <span className="hidden sm:inline">손실 계산기</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>고정손실 계산기</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* 현재 주가 */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
              현재 주가 (원)
            </label>
            <input
              type="number"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="주가 입력"
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* 손절 비율 */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
              손절 비율 (%)
            </label>
            <input
              type="number"
              value={stopLossPct}
              onChange={(e) => setStopLossPct(e.target.value)}
              placeholder="예: 3"
              step="0.1"
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* 고정 손실 금액 */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
              고정 손실 금액 (원)
            </label>
            <input
              type="number"
              value={fixedLoss}
              onChange={(e) => setFixedLoss(e.target.value)}
              placeholder="예: 100000"
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* 결과 */}
          {isValid && (
            <div className="rounded-lg bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-800 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600 dark:text-slate-400">매수 수량</span>
                <span className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                  {shares.toLocaleString("ko-KR")}주
                </span>
              </div>
              <div className="border-t border-indigo-200 dark:border-indigo-700 pt-2 space-y-1">
                <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
                  <span>매수 금액</span>
                  <span>{totalCost.toLocaleString("ko-KR")}원</span>
                </div>
                <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
                  <span>주당 손실</span>
                  <span>{lossPerShare.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}원</span>
                </div>
                <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
                  <span>실제 손실</span>
                  <span>{actualLoss.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}원</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
