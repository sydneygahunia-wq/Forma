"use client";

import { useEffect, useRef, useState } from "react";

import { API_URL, wsUrl } from "@/lib/api";
import type { SimEvent, Snapshot } from "@/lib/types";
import { backoffDelay } from "@/lib/utils";

export type FeedStatus = "connecting" | "live" | "reconnecting" | "polling";

export interface HistoryPoint {
  tick: number;
  shipped: number;
  inProgress: number;
  queued: number;
  utilization: number;
}

const MAX_EVENTS = 40;
const MAX_HISTORY = 180;
const HISTORY_EVERY_TICKS = 4;
const POLL_MS = 1000;

/** Append a history point at most every few ticks so the chart stays readable. */
export function appendHistory(history: HistoryPoint[], snap: Snapshot): HistoryPoint[] {
  let last: HistoryPoint | undefined = history[history.length - 1];
  if (last && snap.tick < last.tick) {
    // The simulation restarted (tick went backwards): start a fresh series.
    // This must run before the sampling check, or the chart would freeze
    // until the new tick caught up with the old one.
    history = [];
    last = undefined;
  }
  if (last && snap.tick - last.tick < HISTORY_EVERY_TICKS) return history;
  const point: HistoryPoint = {
    tick: snap.tick,
    shipped: snap.metrics.orders_shipped,
    inProgress: snap.metrics.orders_in_progress,
    queued: snap.metrics.tasks_queued,
    utilization: Math.round(snap.metrics.utilization * 100),
  };
  return [...history, point].slice(-MAX_HISTORY);
}

/**
 * Live simulation state over a WebSocket.
 *
 * Every message is a *full* snapshot, so the client never has to reconcile
 * deltas: after a dropped connection it simply renders the next snapshot.
 * While disconnected it reconnects with jittered exponential backoff and
 * falls back to polling the REST endpoint so the UI keeps updating.
 */
export function useSimulationFeed() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [events, setEvents] = useState<SimEvent[]>([]);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [status, setStatus] = useState<FeedStatus>("connecting");
  const attempt = useRef(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let disposed = false;

    const onSnapshot = (snap: Snapshot) => {
      setSnapshot(snap);
      setHistory((h) => appendHistory(h, snap));
    };

    const startPolling = () => {
      if (pollTimer) return;
      pollTimer = setInterval(async () => {
        try {
          const res = await fetch(`${API_URL}/api/simulation/state`);
          if (res.ok) {
            onSnapshot(await res.json());
            setStatus((s) => (s === "live" ? s : "polling"));
          }
        } catch {
          /* backend unreachable; keep trying */
        }
      }, POLL_MS);
    };

    const stopPolling = () => {
      clearInterval(pollTimer);
      pollTimer = undefined;
    };

    const connect = () => {
      if (disposed) return;
      ws = new WebSocket(wsUrl("/ws/simulation"));
      ws.onopen = () => {
        attempt.current = 0;
        setStatus("live");
        stopPolling();
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "snapshot") onSnapshot(msg);
        else if (msg.type === "events" && msg.events.length) {
          setEvents((prev) => [...[...msg.events].reverse(), ...prev].slice(0, MAX_EVENTS));
        }
      };
      ws.onclose = () => {
        if (disposed) return;
        setStatus("reconnecting");
        startPolling();
        reconnectTimer = setTimeout(connect, backoffDelay(attempt.current++));
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      stopPolling();
      ws?.close();
    };
  }, []);

  return { snapshot, events, history, status };
}
