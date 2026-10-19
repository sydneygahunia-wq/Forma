import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { checkoutErrorMessage } from "@/components/store/cart-drawer";
import { sortProducts, stockBadge } from "@/components/store/storefront";
import { describeEvent, eventFields } from "@/components/dashboard/dashboard";
import { isWalkable } from "@/components/pathfinding/pathfinding-lab";
import { WarehouseFloor } from "@/components/warehouse/warehouse-floor";
import { ApiError } from "@/lib/api";
import type { Product, Robot, WarehouseLayout } from "@/lib/types";

const layout: WarehouseLayout = {
  width: 4,
  height: 3,
  rows: ["####", "#.S#", "#PH#"],
  shelves: [{ id: 0, pos: [2, 1], access: [1, 1] }],
  pack_stations: [[1, 2]],
  homes: [[2, 2]],
  lanes: { "1,1": [[0, 1]] },
};

const robot = (id: number, state: Robot["state"] = "idle"): Robot => ({
  id,
  pos: [1, 1],
  home: [2, 2],
  state,
  task_id: null,
  path: [],
  distance: 0,
  wait_ticks: 0,
});

describe("WarehouseFloor", () => {
  it("renders the floor, labels stations and docks, and draws every robot", () => {
    const moving = { ...robot(0, "to_shelf"), path: [[1, 2]] as [number, number][] };
    const { container } = render(<WarehouseFloor layout={layout} robots={[moving, robot(1, "offline")]} />);
    expect(screen.getByRole("img", { name: /warehouse/i })).toBeInTheDocument();
    expect(screen.getByText("P1")).toBeInTheDocument(); // pack station label
    expect(screen.getByTestId("robot-0")).toHaveAttribute("data-state", "to_shelf");
    expect(screen.getByTestId("robot-1")).toHaveTextContent("×"); // offline marker
    // A moving robot gets a heading arrow, and its goal gets an orange square.
    expect(screen.getByTestId("robot-0").querySelector("path")).not.toBeNull();
    expect(container.querySelector("rect[stroke='var(--floor-goal)']")).not.toBeNull();
  });
});

describe("store helpers", () => {
  it("labels stock levels", () => {
    expect(stockBadge(0)).toEqual({ label: "Sold out", dark: true });
    expect(stockBadge(3)?.label).toBe("Only 3 left");
    expect(stockBadge(30)).toBeNull();
  });

  it("sorts products", () => {
    const p = (id: number, name: string, price: number) => ({ id, name, price_cents: price }) as Product;
    const list = [p(1, "Mug", 300), p(2, "Apron", 100), p(3, "Lamp", 200)];
    expect(sortProducts(list, "price-asc").map((x) => x.id)).toEqual([2, 3, 1]);
    expect(sortProducts(list, "name").map((x) => x.id)).toEqual([2, 3, 1]);
    expect(sortProducts(list, "featured").map((x) => x.id)).toEqual([1, 2, 3]);
  });

  it("explains checkout errors", () => {
    const oos = new ApiError(409, "out_of_stock", "not enough stock for Mug", { available: 1 });
    expect(checkoutErrorMessage(oos)).toMatch(/Only 1 left/);
    expect(checkoutErrorMessage(new TypeError("fetch failed"))).toMatch(/not duplicated/);
  });
});

describe("dashboard + pathfinding helpers", () => {
  it("describes simulation events", () => {
    expect(describeEvent({ type: "order_shipped", tick: 9, order_id: "abcdef123456", fulfillment_ticks: 40 })).toBe(
      "order abcdef12 shipped in 40 ticks",
    );
    expect(describeEvent({ type: "robot_offline", tick: 1, robot_id: 3 })).toBe("robot 3 went offline");
    expect(eventFields({ type: "task_assigned", tick: 2, robot_id: 1, order_id: "abcdef123456", task_id: 7 })).toBe(
      "robot=1 order=abcdef12 task=7",
    );
  });

  it("knows which cells are walkable", () => {
    expect(isWalkable(layout, [1, 1])).toBe(true);
    expect(isWalkable(layout, [2, 1])).toBe(false); // shelf
    expect(isWalkable(layout, [0, 0])).toBe(false); // wall
  });
});
