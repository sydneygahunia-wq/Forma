"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Check, Panel } from "@/components/console/console-chrome";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { WarehouseFloor } from "@/components/warehouse/warehouse-floor";
import { useSimulationFeed, type FeedStatus, type HistoryPoint } from "@/hooks/use-simulation-feed";
import { api } from "@/lib/api";
import type { Robot, Scheduler, SimEvent, Snapshot } from "@/lib/types";
import { cn, formatCents, shortId } from "@/lib/utils";

const SPEEDS = [0.25, 0.5, 1, 2, 4];
const BASE_TICK_MS = 250;

const FEED: Record<FeedStatus, { dot: string; label: string }> = {
  live: { dot: "bg-success", label: "Live" },
  polling: { dot: "bg-warning", label: "Polling (WebSocket down)" },
  reconnecting: { dot: "bg-danger", label: "Reconnecting…" },
  connecting: { dot: "bg-muted-foreground", label: "Connecting…" },
};

const STATE_LABEL: Record<Robot["state"], string> = {
  idle: "Idle",
  to_shelf: "To shelf",
  picking: "Picking",
  to_pack: "To station",
  dropping: "Dropping",
  returning: "Returning",
  offline: "Offline",
};

/** Human-readable one-liner for an event. */
export function describeEvent(e: SimEvent): string {
  const order = e.order_id ? `order ${shortId(e.order_id)}` : "";
  switch (e.type) {
    case "order_queued":
      return `${order} queued (${e.tasks} pick${e.tasks === 1 ? "" : "s"})`;
    case "task_assigned":
      return `robot ${e.robot_id} assigned to ${order}`;
    case "task_picked":
      return `robot ${e.robot_id} picked an item for ${order}`;
    case "task_delivered":
      return `robot ${e.robot_id} dropped an item at packing`;
    case "order_packing":
      return `${order} is being packed`;
    case "order_shipped":
      return `${order} shipped in ${e.fulfillment_ticks} ticks`;
    case "robot_offline":
      return `robot ${e.robot_id} went offline`;
    case "robot_online":
      return `robot ${e.robot_id} back online`;
    case "task_requeued":
      return `task for ${order} re-queued`;
    case "robot_yield":
      return `robot ${e.robot_id} yielded to robot ${e.blocker}`;
    default:
      return e.type;
  }
}

/** Key=value fields of an event, as a raw log would show them. */
export function eventFields(e: SimEvent): string {
  const parts: string[] = [];
  if (e.robot_id !== undefined) parts.push(`robot=${e.robot_id}`);
  if (e.order_id) parts.push(`order=${shortId(e.order_id)}`);
  if (e.task_id !== undefined) parts.push(`task=${e.task_id}`);
  if (e.fulfillment_ticks !== undefined) parts.push(`ticks=${e.fulfillment_ticks}`);
  if (e.blocker !== undefined) parts.push(`blocker=${e.blocker}`);
  if (e.tasks !== undefined) parts.push(`picks=${e.tasks}`);
  return parts.join(" ");
}

type View = Record<"grid" | "ids" | "goals" | "paths" | "lanes" | "axes", boolean>;

function Section({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("border-b border-border px-3 py-3", className)}>
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </div>
  );
}

function Sidebar({
  snapshot,
  status,
  view,
  setView,
  selected,
  setSelected,
  revenue,
}: {
  snapshot: Snapshot | null;
  status: FeedStatus;
  view: View;
  setView: (v: View) => void;
  selected: number | null;
  setSelected: (id: number | null) => void;
  revenue?: number;
}) {
  const command = useMutation({ mutationFn: api.command });
  const feed = FEED[status];
  const taskById = new Map(snapshot?.tasks.map((t) => [t.id, t]) ?? []);
  const speed = snapshot ? BASE_TICK_MS / snapshot.tick_interval_ms : 1;
  const m = snapshot?.metrics;

  return (
    <Panel title="Simulation" bodyClassName="grid content-start text-[13px] md:grid-cols-2 xl:grid-cols-1">
      <Section title="Time">
        <p className="font-mono text-[28px] leading-none tabular-nums">
          {snapshot ? String(snapshot.tick).padStart(5, "0") : "-----"}
        </p>
        <p className="mt-2 flex items-center gap-1.5 text-[12px] text-muted-foreground" data-testid="feed-status">
          <span className={cn("h-2 w-2 rounded-full", feed.dot)} />
          {feed.label}
          {snapshot && ` · ${(1000 / snapshot.tick_interval_ms).toFixed(1)} ticks/s`}
          {snapshot?.paused && " · paused"}
        </p>
      </Section>

      {snapshot && (
        <Section title="Playback">
          <div className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2">
            <Button
              variant="console"
              size="xs"
              className="col-span-2 h-7 justify-self-start px-3"
              onClick={() => command.mutate({ action: snapshot.paused ? "resume" : "pause" })}
            >
              {snapshot.paused ? "Resume" : "Pause"}
            </Button>
            <label htmlFor="speed" className="text-muted-foreground">
              Speed
            </label>
            <Select
              id="speed"
              value={SPEEDS.find((s) => Math.abs(s - speed) < 0.01) ?? 1}
              onChange={(e) =>
                command.mutate({ action: "speed", tick_interval_ms: Math.round(BASE_TICK_MS / Number(e.target.value)) })
              }
            >
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </Select>
            <label htmlFor="scheduler" className="text-muted-foreground">
              Scheduler
            </label>
            <Select
              id="scheduler"
              value={snapshot.scheduler}
              onChange={(e) => command.mutate({ action: "scheduler", name: e.target.value as Scheduler })}
            >
              <option value="fifo">FIFO (baseline)</option>
              <option value="nearest">Nearest robot</option>
              <option value="batch_greedy">Batch greedy</option>
            </Select>
          </div>
        </Section>
      )}

      <Section title="Display">
        <div className="grid gap-1.5">
          <Check checked={view.grid} onChange={(v) => setView({ ...view, grid: v })}>
            Show grid
          </Check>
          <Check checked={view.ids} onChange={(v) => setView({ ...view, ids: v })}>
            Show robot IDs
          </Check>
          <Check checked={view.goals} onChange={(v) => setView({ ...view, goals: v })}>
            Show goal locations
          </Check>
          <Check checked={view.paths} onChange={(v) => setView({ ...view, paths: v })}>
            Show planned paths
          </Check>
          <Check checked={view.lanes} onChange={(v) => setView({ ...view, lanes: v })}>
            Show one-way lanes
          </Check>
          <Check checked={view.axes} onChange={(v) => setView({ ...view, axes: v })}>
            Show coordinates
          </Check>
        </div>
      </Section>

      <Section title={`Robots (${snapshot?.robots.length ?? 0})`} className="md:col-span-2 xl:col-span-1">
        <table className="w-full text-[12px]">
          <thead className="text-left text-[11px] text-muted-foreground">
            <tr className="border-b border-border">
              <th className="py-1 pr-2 font-medium">Robot</th>
              <th className="py-1 pr-2 font-medium">Status</th>
              <th className="py-1 pr-2 font-medium">Item</th>
              <th className="py-1 pr-2 font-medium">Cell</th>
              <th className="py-1 text-right font-medium">Breakdown</th>
            </tr>
          </thead>
          <tbody>
            {snapshot?.robots.map((r) => {
              const task = r.task_id !== null ? taskById.get(r.task_id) : undefined;
              const offline = r.state === "offline";
              return (
                <tr
                  key={r.id}
                  onClick={() => setSelected(selected === r.id ? null : r.id)}
                  className={cn(
                    "cursor-pointer border-b border-border/70 last:border-0",
                    selected === r.id ? "bg-[#fff4e6]" : "hover:bg-muted",
                  )}
                  aria-selected={selected === r.id}
                >
                  <td className="py-1 pr-2 font-mono">R{r.id}</td>
                  <td className={cn("py-1 pr-2", offline && "text-danger")}>{STATE_LABEL[r.state]}</td>
                  <td className="py-1 pr-2 font-mono text-[11px] text-muted-foreground">{task?.sku ?? "-"}</td>
                  <td className="py-1 pr-2 font-mono text-[11px] text-muted-foreground">
                    {r.pos[0]},{r.pos[1]}
                  </td>
                  <td className="py-1 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        command.mutate({ action: "robot", robot_id: r.id, online: offline });
                      }}
                      className={cn(
                        "cursor-pointer whitespace-nowrap text-[12px] hover:underline",
                        offline ? "text-success" : "text-primary",
                      )}
                      title={
                        offline
                          ? "Repair this robot and return it to service"
                          : "Simulate a breakdown: the robot stops and its job goes to another robot"
                      }
                    >
                      {offline ? "Bring online" : "Take offline"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
          Click a row to highlight that robot’s route. <b className="font-medium text-foreground">Take offline</b>{" "}
          simulates a breakdown: the robot stops where it is, the others drive around it, and its job is handed to
          another robot.
        </p>
      </Section>

      <Section title="Statistics">
        <dl className="grid grid-cols-[1fr_auto] gap-y-1 text-[12px]">
          {(
            [
              ["Orders shipped", m?.orders_shipped],
              ["Orders in progress", m?.orders_in_progress],
              ["Picks waiting", m?.tasks_queued],
              ["Avg fulfillment", m?.avg_fulfillment_ticks != null ? `${m.avg_fulfillment_ticks} ticks` : undefined],
              ["Fleet utilization", m ? `${(m.utilization * 100).toFixed(1)}%` : undefined],
              ["Distance travelled", m?.total_distance],
              ["Wait ticks", m?.total_wait_ticks],
              ["Replans", m?.total_replans],
              ["Revenue", revenue !== undefined ? formatCents(revenue) : undefined],
            ] as [string, string | number | undefined][]
          ).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="text-right font-mono tabular-nums">{v ?? "-"}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </Panel>
  );
}

function TaskTable({ snapshot }: { snapshot: Snapshot | null }) {
  const tasks = snapshot?.tasks ?? [];
  return (
    <table className="w-full text-[12px]">
      <thead className="sticky top-0 bg-panel text-left text-muted-foreground">
        <tr className="border-b border-border">
          <th className="px-3 py-1.5 font-medium">Task</th>
          <th className="py-1.5 font-medium">Order</th>
          <th className="py-1.5 font-medium">Item</th>
          <th className="py-1.5 font-medium">Robot</th>
          <th className="py-1.5 pr-3 font-medium">Status</th>
        </tr>
      </thead>
      <tbody className="font-mono text-[11.5px]">
        {tasks.length === 0 && (
          <tr>
            <td colSpan={5} className="px-3 py-3 font-sans text-muted-foreground">
              No open tasks. Place an order in the storefront.
            </td>
          </tr>
        )}
        {tasks.map((t) => (
          <tr key={t.id} className="border-b border-border/70">
            <td className="px-3 py-1">{t.id}</td>
            <td className="py-1">{shortId(t.order_id)}</td>
            <td className="py-1">
              {t.sku} ×{t.quantity}
            </td>
            <td className="py-1">{t.robot_id ?? "-"}</td>
            <td className="py-1 pr-3 font-sans">{t.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EventLog({ events }: { events: SimEvent[] }) {
  return (
    <ol className="text-[12px]" data-testid="event-feed">
      {events.length === 0 && <li className="px-3 py-3 text-muted-foreground">No events yet.</li>}
      {events.map((e, i) => (
        <li key={`${e.tick}-${i}`} className="flex gap-3 border-b border-border/70 px-3 py-1" title={eventFields(e)}>
          <span className="w-10 shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">{e.tick}</span>
          <span
            className={cn(
              "truncate",
              e.type === "robot_offline" || e.type === "task_requeued"
                ? "text-danger"
                : e.type === "order_shipped" && "text-success",
            )}
          >
            {describeEvent(e)}
          </span>
        </li>
      ))}
    </ol>
  );
}

const AXIS = { fontSize: 10, fill: "#6b6b6b" };

function Throughput({ history }: { history: HistoryPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={history} margin={{ top: 10, right: 14, bottom: 0, left: -16 }}>
        <CartesianGrid stroke="#ececec" />
        <XAxis dataKey="tick" tick={AXIS} stroke="#c4c4c4" minTickGap={40} />
        <YAxis tick={AXIS} stroke="#c4c4c4" allowDecimals={false} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #d9d9d9" }}
          labelFormatter={(t) => `tick ${t}`}
        />
        <Line dataKey="shipped" name="Shipped" stroke="#2b7bd6" strokeWidth={1.5} dot={false} isAnimationActive={false} />
        <Line dataKey="inProgress" name="In progress" stroke="#f28c28" strokeWidth={1.5} dot={false} isAnimationActive={false} />
        <Line dataKey="queued" name="Picks waiting" stroke="#8a8a8a" strokeWidth={1} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Dashboard() {
  const { snapshot, events, history, status } = useSimulationFeed();
  const layout = useQuery({ queryKey: ["layout"], queryFn: api.layout, staleTime: Infinity });
  const store = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 3000 });
  const [view, setView] = useState<View>({ grid: true, ids: true, goals: true, paths: false, lanes: false, axes: true });
  const [selected, setSelected] = useState<number | null>(null);

  return (
    <div className="grid min-h-0 flex-1 gap-2 p-2 xl:h-[calc(100vh-44px)] xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="grid min-h-0 gap-2 xl:grid-rows-[minmax(0,1fr)_220px]">
        <Panel
          title="Floor"
          actions={
            <span className="text-[12px]">
              {layout.data ? `${layout.data.width} × ${layout.data.height} grid · ${layout.data.shelves.length} shelves` : ""}
            </span>
          }
          bodyClassName="flex items-center justify-center overflow-hidden bg-[#f7f7f7] p-4"
        >
          {layout.data ? (
            <WarehouseFloor
              layout={layout.data}
              robots={snapshot?.robots}
              tasks={snapshot?.tasks}
              tickMs={snapshot?.tick_interval_ms}
              showGrid={view.grid}
              showIds={view.ids}
              showGoals={view.goals}
              showPaths={view.paths}
              showLanes={view.lanes}
              showAxes={view.axes}
              selectedRobot={selected}
              onRobotClick={(id) => setSelected(selected === id ? null : id)}
              className="h-full max-w-full"
            />
          ) : (
            <div className="aspect-[26/14] w-full bg-muted" />
          )}
        </Panel>

        <div className="grid min-h-[220px] gap-2 lg:grid-cols-3">
          <Panel title={`Tasks (${snapshot?.tasks.length ?? 0})`}>
            <TaskTable snapshot={snapshot} />
          </Panel>
          <Panel title="Event log">
            <EventLog events={events} />
          </Panel>
          <Panel title="Throughput" className="min-h-[220px]" bodyClassName="overflow-hidden">
            <Throughput history={history} />
          </Panel>
        </div>
      </div>

      <Sidebar
        snapshot={snapshot}
        status={status}
        view={view}
        setView={setView}
        selected={selected}
        setSelected={setSelected}
        revenue={store.data?.store.revenue_cents}
      />
    </div>
  );
}
