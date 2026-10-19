"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Panel } from "@/components/console/console-chrome";
import { WarehouseFloor } from "@/components/warehouse/warehouse-floor";
import { api } from "@/lib/api";
import type { Pos, WarehouseLayout } from "@/lib/types";
import { cn } from "@/lib/utils";

type Algo = "bfs" | "dijkstra" | "astar";

const ALGOS: { key: Algo; label: string; note: string }[] = [
  { key: "bfs", label: "BFS", note: "Expands nodes in order of discovery (FIFO queue). Optimal only when every step costs the same." },
  { key: "dijkstra", label: "Dijkstra", note: "Expands the node with the lowest cost so far g(n), using a priority queue. Optimal for any non-negative costs." },
  { key: "astar", label: "A*", note: "Orders the queue by g(n) + h(n), where h is the Manhattan distance to the goal. h never overestimates, so A* is still optimal." },
];

export function isWalkable(layout: WarehouseLayout, [x, y]: Pos): boolean {
  const ch = layout.rows[y]?.[x];
  return ch === "." || ch === "P" || ch === "H";
}

export function PathfindingLab() {
  const layout = useQuery({ queryKey: ["layout"], queryFn: api.layout, staleTime: Infinity });
  const [start, setStart] = useState<Pos>([1, 2]);
  const [goal, setGoal] = useState<Pos>([22, 12]);
  const [picking, setPicking] = useState<"start" | "goal">("start");
  const [algo, setAlgo] = useState<Algo>("astar");

  const result = useQuery({
    queryKey: ["paths", start, goal],
    queryFn: () => api.comparePaths(start.join(","), goal.join(",")),
    enabled: layout.isSuccess,
  });

  const onCellClick = (pos: Pos) => {
    if (!layout.data || !isWalkable(layout.data, pos)) return;
    if (picking === "start") setStart(pos);
    else setGoal(pos);
    setPicking(picking === "start" ? "goal" : "start");
  };

  const selected = result.data?.[algo];
  const meta = ALGOS.find((a) => a.key === algo)!;
  const maxExpanded = Math.max(1, ...ALGOS.map((a) => result.data?.[a.key].expanded ?? 0));

  return (
    <div className="grid min-h-0 flex-1 gap-2 p-2 xl:h-[calc(100vh-44px)] xl:grid-cols-[minmax(0,1fr)_320px]">
      <Panel
        title="Planner"
        actions={
          <span className="text-[12px]">
            Click a free cell to set the <b className="font-semibold text-foreground">{picking}</b>
          </span>
        }
        bodyClassName="flex flex-col overflow-hidden"
      >
        <div className="flex items-center gap-3 border-b border-border px-3 py-2 text-[13px]">
          <div className="inline-flex overflow-hidden rounded border border-border-strong" role="group" aria-label="Algorithm">
            {ALGOS.map((a) => (
              <button
                key={a.key}
                onClick={() => setAlgo(a.key)}
                aria-pressed={algo === a.key}
                className={cn(
                  "cursor-pointer border-r border-border-strong px-3 py-1 last:border-r-0",
                  algo === a.key ? "bg-primary text-primary-foreground" : "bg-panel hover:bg-muted",
                )}
              >
                {a.label}
              </button>
            ))}
          </div>
          <span className="ml-auto font-mono text-[12px] text-muted-foreground">
            start ({start.join(", ")}) → goal ({goal.join(", ")})
          </span>
        </div>
        <div className="flex min-h-0 flex-1 items-center justify-center bg-[#f7f7f7] p-4">
          {layout.data && (
            <WarehouseFloor
              layout={layout.data}
              visited={selected?.visited}
              visitedColor="#2b7bd6"
              overlays={selected?.path ? [{ cells: selected.path, color: "#f28c28" }] : []}
              markers={[
                { pos: start, label: "S", color: "#1a7f37" },
                { pos: goal, label: "G", color: "#cf222e" },
              ]}
              showAxes
              showLanes
              showGoals={false}
              onCellClick={onCellClick}
              className="h-full max-w-full"
            />
          )}
        </div>
        <p className="border-t border-border px-3 py-1.5 text-[12px] text-muted-foreground">
          Blue cells: nodes expanded. Orange line: path found. Arrows: one-way lanes the search must obey.
        </p>
      </Panel>

      <div className="grid min-h-0 content-start gap-2">
        <Panel title={`Result: ${meta.label}`}>
          <dl className="grid grid-cols-[1fr_auto] gap-y-1 px-3 py-2 text-[13px]">
            <dt className="text-muted-foreground">Path cost</dt>
            <dd className="text-right font-mono" data-testid="path-cost">
              {selected ? (selected.cost ?? "unreachable") : "-"}
            </dd>
            <dt className="text-muted-foreground">Nodes expanded</dt>
            <dd className="text-right font-mono" data-testid="path-expanded">
              {selected?.expanded ?? "-"}
            </dd>
          </dl>
          <p className="border-t border-border px-3 py-2 text-[12px] leading-relaxed text-muted-foreground">{meta.note}</p>
        </Panel>

        <Panel title="Same query, three algorithms">
          <table className="w-full text-[13px]">
            <thead className="text-left text-[12px] text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-3 py-1.5 font-medium">Algorithm</th>
                <th className="py-1.5 font-medium">Expanded</th>
                <th className="py-1.5 pr-3 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {ALGOS.map((a) => {
                const r = result.data?.[a.key];
                return (
                  <tr key={a.key} className={cn("border-b border-border/70", a.key === algo && "bg-muted")}>
                    <td className="px-3 py-1.5">{a.label}</td>
                    <td className="py-1.5">
                      <div className="flex items-center gap-2">
                        <div className="h-2 flex-1 bg-[#ececec]">
                          <div className="h-full bg-[#2b7bd6]" style={{ width: `${((r?.expanded ?? 0) / maxExpanded) * 100}%` }} />
                        </div>
                        <span className="w-8 text-right font-mono text-[12px]">{r?.expanded ?? "-"}</span>
                      </div>
                    </td>
                    <td className="py-1.5 pr-3 text-right font-mono text-[12px]">{r?.cost ?? "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="px-3 py-2 text-[12px] text-muted-foreground">
            All three find the same optimal cost. The heuristic is what lets A* skip most of the floor.
          </p>
        </Panel>
      </div>
    </div>
  );
}
