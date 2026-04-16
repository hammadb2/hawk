"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  onSign: (signatureData: string) => void;
  onCancel: () => void;
}

export function OnboardingSignaturePad({ onSign, onCancel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [drawing, setDrawing] = useState(false);
  const [hasDrawn, setHasDrawn] = useState(false);

  const getCtx = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    return canvas.getContext("2d");
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#161625";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#10b981";
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
  }, []);

  function getPos(e: React.MouseEvent | React.TouchEvent) {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    if ("touches" in e) {
      return {
        x: e.touches[0].clientX - rect.left,
        y: e.touches[0].clientY - rect.top,
      };
    }
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function startDraw(e: React.MouseEvent | React.TouchEvent) {
    const ctx = getCtx();
    if (!ctx) return;
    setDrawing(true);
    setHasDrawn(true);
    const pos = getPos(e);
    ctx.beginPath();
    ctx.moveTo(pos.x, pos.y);
  }

  function draw(e: React.MouseEvent | React.TouchEvent) {
    if (!drawing) return;
    const ctx = getCtx();
    if (!ctx) return;
    const pos = getPos(e);
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
  }

  function stopDraw() {
    setDrawing(false);
  }

  function clear() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#161625";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    setHasDrawn(false);
  }

  function submit() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const data = canvas.toDataURL("image/png");
    onSign(data);
  }

  return (
    <div className="space-y-3">
      <canvas
        ref={canvasRef}
        width={500}
        height={200}
        className="w-full rounded-lg border border-slate-700 cursor-crosshair touch-none"
        onMouseDown={startDraw}
        onMouseMove={draw}
        onMouseUp={stopDraw}
        onMouseLeave={stopDraw}
        onTouchStart={startDraw}
        onTouchMove={draw}
        onTouchEnd={stopDraw}
      />
      <div className="flex gap-2">
        <button
          onClick={submit}
          disabled={!hasDrawn}
          className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50 transition"
        >
          Confirm Signature
        </button>
        <button
          onClick={clear}
          className="rounded-lg bg-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-600 transition"
        >
          Clear
        </button>
        <button
          onClick={onCancel}
          className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white transition"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
