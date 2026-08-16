"use client";
/* Inline telemetry sparkline — canvas, no dependencies.

   An ops console with zero charts undersells the Grafana track, and the shape
   of a signal is the thing the Studio Head actually reads: these are drawn from
   the very samples the Metrics Analyst already retrieved through the MCP
   server, so the line and the number can never disagree. Nothing is drawn when
   there is nothing to draw. */

import { useEffect, useRef } from "react";

const PAD = 2;

export function Sparkline({
  samples,
  anomalous = false,
  width = 132,
  height = 30,
  label,
}: {
  /** [timestamp, value] pairs straight off the TelemetryEvidence record. */
  samples: [number, number][];
  anomalous?: boolean;
  width?: number;
  height?: number;
  label?: string;
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || samples.length < 2) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Draw at device resolution so the line stays crisp when recording.
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const css = getComputedStyle(canvas);
    const stroke = css.getPropertyValue(anomalous ? "--warn" : "--accent").trim() || "#888";
    const values = samples.map(([, v]) => v);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const stepX = (width - PAD * 2) / (samples.length - 1);
    const y = (v: number) => height - PAD - ((v - min) / span) * (height - PAD * 2);

    const trace = () => {
      ctx.beginPath();
      samples.forEach(([, v], i) => {
        const px = PAD + i * stepX;
        if (i === 0) ctx.moveTo(px, y(v));
        else ctx.lineTo(px, y(v));
      });
    };

    // Soft fill under the line, then the line itself.
    trace();
    ctx.lineTo(width - PAD, height);
    ctx.lineTo(PAD, height);
    ctx.closePath();
    ctx.fillStyle = stroke;
    ctx.globalAlpha = 0.12;
    ctx.fill();
    ctx.globalAlpha = 1;

    trace();
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    ctx.stroke();

    // The latest reading gets a dot — where the signal is right now.
    const lastX = PAD + (samples.length - 1) * stepX;
    const lastY = y(values[values.length - 1]);
    ctx.beginPath();
    ctx.arc(lastX, lastY, 2.2, 0, Math.PI * 2);
    ctx.fillStyle = stroke;
    ctx.fill();
  }, [samples, anomalous, width, height]);

  if (samples.length < 2) return null;
  const values = samples.map(([, v]) => v);
  return (
    <canvas
      ref={ref}
      style={{ width, height, display: "block", marginTop: 6 }}
      role="img"
      aria-label={
        label
          ? `${label} sparkline, ${samples.length} samples, ` +
            `low ${Math.min(...values)}, high ${Math.max(...values)}`
          : "telemetry sparkline"
      }
    />
  );
}
