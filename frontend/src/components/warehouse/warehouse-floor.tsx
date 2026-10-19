"use client";

import { memo, type CSSProperties } from "react";

import type { Pos, Robot, SimTask, WarehouseLayout } from "@/lib/types";
import { cn } from "@/lib/utils";

/*
 * Top-down floor view in the style of multi-robot research simulators
 * (PlanViz for the League of Robot Runners, RWARE, MAPF visualisers):
 * white cells on a thin grid, solid black obstacles, flat shelf squares,
 * every robot the same colour with its state shown by fill, goals as orange
 * squares. Deliberately plain: it is a debugging view, not an illustration.
 */

export const CELL = 22;
const AXIS = 14;

export interface PathOverlay {
  cells: Pos[];
  color: string;
}

interface Props {
  layout: WarehouseLayout;
  robots?: Robot[];
  tasks?: SimTask[];
  tickMs?: number;
  showGrid?: boolean;
  showIds?: boolean;
  showLanes?: boolean;
  showPaths?: boolean;
  showGoals?: boolean;
  showAxes?: boolean;
  /** Robots working on this order are drawn in colour; the rest in grey. */
  highlightOrder?: string;
  selectedRobot?: number | null;
  onRobotClick?: (id: number) => void;
  visited?: Pos[];
  visitedColor?: string;
  overlays?: PathOverlay[];
  markers?: { pos: Pos; label: string; color: string }[];
  onCellClick?: (pos: Pos) => void;
  className?: string;
}

const ARROW: Record<string, string> = { "0,-1": "↑", "0,1": "↓", "-1,0": "←", "1,0": "→" };

const StaticFloor = memo(function StaticFloor({
  layout,
  showGrid,
  showLanes,
  showAxes,
}: {
  layout: WarehouseLayout;
  showGrid: boolean;
  showLanes: boolean;
  showAxes: boolean;
}) {
  const w = layout.width * CELL;
  const h = layout.height * CELL;
  const packIndex = new Map(layout.pack_stations.map((p, i) => [p.join(","), i + 1]));

  return (
    <g shapeRendering="crispEdges">
      <defs>
        <pattern id="floor-grid" width={CELL} height={CELL} patternUnits="userSpaceOnUse">
          <path d={`M ${CELL} 0 L 0 0 0 ${CELL}`} fill="none" stroke="var(--floor-grid)" strokeWidth={1} />
        </pattern>
      </defs>
      <rect width={w} height={h} fill="var(--floor-bg)" />
      {showGrid && <rect width={w} height={h} fill="url(#floor-grid)" />}

      {layout.rows.map((row, y) =>
        [...row].map((ch, x) => {
          const px = x * CELL;
          const py = y * CELL;
          const key = `${x},${y}`;
          if (ch === "#" || ch === "X") {
            return <rect key={key} x={px} y={py} width={CELL} height={CELL} fill="var(--floor-wall)" />;
          }
          if (ch === "S") {
            return (
              <rect key={key} x={px + 1} y={py + 1} width={CELL - 2} height={CELL - 2} fill="var(--floor-shelf)" />
            );
          }
          if (ch === "P") {
            return (
              <g key={key}>
                <rect x={px + 1} y={py + 1} width={CELL - 2} height={CELL - 2} fill="var(--floor-pack)" />
                <text
                  x={px + CELL / 2}
                  y={py + CELL / 2 + 3}
                  textAnchor="middle"
                  fontSize={8}
                  fill="#fff"
                  shapeRendering="auto"
                >
                  P{packIndex.get(key)}
                </text>
              </g>
            );
          }
          if (ch === "H") {
            return (
              <rect key={key} x={px + 1} y={py + 1} width={CELL - 2} height={CELL - 2} fill="var(--floor-dock)" />
            );
          }
          return null;
        }),
      )}

      {showLanes &&
        Object.entries(layout.lanes).map(([key, dirs]) => {
          const main = dirs.length === 1 ? dirs[0] : dirs.find(([dx]) => dx !== 0);
          if (!main) return null;
          const [x, y] = key.split(",").map(Number);
          return (
            <text
              key={`l${key}`}
              x={x * CELL + CELL / 2}
              y={y * CELL + CELL / 2 + 3}
              textAnchor="middle"
              fontSize={9}
              fill="var(--floor-label)"
              shapeRendering="auto"
            >
              {ARROW[`${main[0]},${main[1]}`]}
            </text>
          );
        })}

      {showAxes && (
        <g fontSize={7.5} fill="var(--floor-label)" shapeRendering="auto" className="font-mono">
          {Array.from({ length: layout.width }, (_, x) => (
            <text key={`ax${x}`} x={x * CELL + CELL / 2} y={h + 10} textAnchor="middle">
              {x}
            </text>
          ))}
          {Array.from({ length: layout.height }, (_, y) => (
            <text key={`ay${y}`} x={-4} y={y * CELL + CELL / 2 + 3} textAnchor="end">
              {y}
            </text>
          ))}
        </g>
      )}
    </g>
  );
});

function center([x, y]: Pos): [number, number] {
  return [x * CELL + CELL / 2, y * CELL + CELL / 2];
}

function polyline(cells: Pos[]): string {
  return cells.map((p) => center(p).join(",")).join(" ");
}

const ACTIVE = new Set(["to_shelf", "picking", "to_pack", "dropping"]);

export function WarehouseFloor({
  layout,
  robots = [],
  tasks = [],
  tickMs = 250,
  showGrid = true,
  showIds = true,
  showLanes = false,
  showPaths = false,
  showGoals = true,
  showAxes = false,
  highlightOrder,
  selectedRobot = null,
  onRobotClick,
  visited,
  visitedColor = "#2b7bd6",
  overlays = [],
  markers = [],
  onCellClick,
  className,
}: Props) {
  const taskById = new Map(tasks.map((t) => [t.id, t]));
  const w = layout.width * CELL;
  const h = layout.height * CELL;
  const padL = showAxes ? AXIS : 0;
  const padB = showAxes ? AXIS : 0;
  const inOrder = (r: Robot) =>
    highlightOrder === undefined || taskById.get(r.task_id ?? -1)?.order_id === highlightOrder;

  // Shelves with an item being fetched are shown in the "requested" colour.
  const activeShelves = new Set(
    tasks
      .filter((t) => t.robot_id !== null && t.status === "assigned")
      .filter((t) => highlightOrder === undefined || t.order_id === highlightOrder)
      .map((t) => t.shelf_id),
  );

  const handleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!onCellClick) return;
    const pt = e.currentTarget.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const local = pt.matrixTransform(e.currentTarget.getScreenCTM()?.inverse());
    const x = Math.floor(local.x / CELL);
    const y = Math.floor(local.y / CELL);
    if (x >= 0 && y >= 0 && x < layout.width && y < layout.height) onCellClick([x, y]);
  };

  const selected = robots.find((r) => r.id === selectedRobot);

  return (
    <svg
      viewBox={`${-padL} 0 ${w + padL} ${h + padB}`}
      className={cn("block h-auto w-full select-none", onCellClick && "cursor-crosshair", className)}
      style={{ "--tick-ms": `${tickMs}ms` } as CSSProperties}
      onClick={handleClick}
      role="img"
      aria-label="Warehouse floor plan"
      fontFamily="var(--font-geist-sans)"
    >
      <StaticFloor layout={layout} showGrid={showGrid} showLanes={showLanes} showAxes={showAxes} />

      {[...activeShelves].map((id) => {
        const shelf = layout.shelves[id];
        if (!shelf) return null;
        return (
          <rect
            key={`as${id}`}
            x={shelf.pos[0] * CELL + 1}
            y={shelf.pos[1] * CELL + 1}
            width={CELL - 2}
            height={CELL - 2}
            fill="var(--floor-shelf-active)"
            shapeRendering="crispEdges"
          />
        );
      })}

      {visited?.map(([x, y]) => (
        <rect
          key={`v${x},${y}`}
          x={x * CELL + 1}
          y={y * CELL + 1}
          width={CELL - 2}
          height={CELL - 2}
          fill={visitedColor}
          opacity={0.18}
          shapeRendering="crispEdges"
        />
      ))}

      {overlays.map((o, i) => (
        <polyline
          key={i}
          points={polyline(o.cells)}
          fill="none"
          stroke={o.color}
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}

      {showPaths &&
        robots.map((r) =>
          r.path.length && r.id !== selectedRobot && inOrder(r) ? (
            <polyline
              key={`p${r.id}`}
              points={polyline([r.pos, ...r.path])}
              fill="none"
              stroke="var(--floor-robot)"
              strokeWidth={1}
              opacity={0.5}
            />
          ) : null,
        )}

      {showGoals &&
        robots.map((r) => {
          if (!r.path.length || r.state === "returning" || !inOrder(r)) return null;
          const [gx, gy] = r.path[r.path.length - 1];
          return (
            <rect
              key={`g${r.id}`}
              x={gx * CELL + 3}
              y={gy * CELL + 3}
              width={CELL - 6}
              height={CELL - 6}
              fill="none"
              stroke="var(--floor-goal)"
              strokeWidth={2}
            />
          );
        })}

      {selected && selected.path.length > 0 && (
        <polyline
          points={polyline([selected.pos, ...selected.path])}
          fill="none"
          stroke="var(--floor-select)"
          strokeWidth={2.5}
          strokeLinejoin="round"
        />
      )}

      {markers.map((m, i) => {
        const [cx, cy] = center(m.pos);
        return (
          <g key={`m${i}`}>
            <rect x={cx - CELL / 2 + 2} y={cy - CELL / 2 + 2} width={CELL - 4} height={CELL - 4} fill={m.color} />
            <text x={cx} y={cy + 3.5} textAnchor="middle" fontSize={10} fontWeight={600} fill="#fff">
              {m.label}
            </text>
          </g>
        );
      })}

      {robots.map((r) => {
        const offline = r.state === "offline";
        const carrying = r.state === "to_pack" || r.state === "dropping";
        const lit = inOrder(r) && ACTIVE.has(r.state);
        const fill = offline ? "#ffffff" : lit ? "var(--floor-robot)" : "var(--floor-robot-idle)";
        const edge = offline ? "var(--danger, #cf222e)" : lit ? "var(--floor-robot-edge)" : "#7d838a";
        const next = r.path[0];
        const heading = next ? [next[0] - r.pos[0], next[1] - r.pos[1]] : null;
        const radius = CELL * 0.4;
        const task = r.task_id !== null ? taskById.get(r.task_id) : undefined;
        return (
          <g
            key={`r${r.id}`}
            className={cn("robot", onRobotClick && "cursor-pointer")}
            style={{ transform: `translate(${r.pos[0] * CELL + CELL / 2}px, ${r.pos[1] * CELL + CELL / 2}px)` }}
            data-testid={`robot-${r.id}`}
            data-state={r.state}
            onClick={
              onRobotClick
                ? (e) => {
                    e.stopPropagation();
                    onRobotClick(r.id);
                  }
                : undefined
            }
          >
            {r.id === selectedRobot && (
              <circle r={radius + 3} fill="none" stroke="var(--floor-select)" strokeWidth={2} />
            )}
            {/* A carried tote is drawn under the robot, like a lifted shelf in RWARE. */}
            {carrying && (
              <rect
                x={-CELL / 2 + 1}
                y={-CELL / 2 + 1}
                width={CELL - 2}
                height={CELL - 2}
                fill="var(--floor-shelf-active)"
                opacity={lit ? 1 : 0.35}
              />
            )}
            <circle r={radius} fill={fill} stroke={edge} strokeWidth={1} />
            {heading && !offline && (
              <path
                d="M0,-2.2 L2.2,0 L0,2.2 Z"
                fill="#fff"
                transform={`rotate(${Math.atan2(heading[1], heading[0]) * (180 / Math.PI)}) translate(${radius - 2.8} 0)`}
              />
            )}
            {showIds && (
              <text
                // Nudge the ID away from the heading arrow so they don't collide.
                x={heading && !offline ? -heading[0] * 1.8 : 0}
                y={3 - (heading && !offline ? heading[1] * 1.8 : 0)}
                textAnchor="middle"
                fontSize={8}
                fontWeight={600}
                fill={offline ? "var(--danger, #cf222e)" : "#fff"}
              >
                {offline ? "×" : r.id}
              </text>
            )}
            <title>{`Robot ${r.id} · ${r.state} · (${r.pos[0]}, ${r.pos[1]})${task ? ` · ${task.sku} ×${task.quantity}` : ""}`}</title>
          </g>
        );
      })}
    </svg>
  );
}
