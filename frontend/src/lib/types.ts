// Mirrors backend/app/schemas.py and the simulation snapshot shape.

export type Pos = [number, number];

export interface Product {
  id: number;
  sku: string;
  name: string;
  description: string;
  category: string;
  image_url: string | null;
  price_cents: number;
  stock: number;
}

export interface CartLine {
  product: Product;
  quantity: number;
  line_total_cents: number;
}

export interface Cart {
  id: string;
  status: "open" | "checked_out";
  items: CartLine[];
  total_cents: number;
}

export type OrderStatus = "placed" | "picking" | "packing" | "shipped";

export interface OrderLine {
  product_id: number;
  sku: string;
  name: string;
  image_url: string | null;
  quantity: number;
  unit_price_cents: number;
}

export interface OrderEvent {
  status: OrderStatus;
  message: string;
  created_at: string;
}

export interface Order {
  id: string;
  status: OrderStatus;
  customer_email: string;
  total_cents: number;
  created_at: string;
  shipped_at: string | null;
  items: OrderLine[];
  events: OrderEvent[];
}

export interface OrderSummary {
  id: string;
  status: OrderStatus;
  total_cents: number;
  item_count: number;
  created_at: string;
}

export interface WarehouseLayout {
  width: number;
  height: number;
  rows: string[];
  shelves: { id: number; pos: Pos; access: Pos }[];
  pack_stations: Pos[];
  homes: Pos[];
  lanes: Record<string, Pos[]>; // "x,y" -> allowed directions
}

export type RobotState =
  | "idle"
  | "to_shelf"
  | "picking"
  | "to_pack"
  | "dropping"
  | "returning"
  | "offline";

export interface Robot {
  id: number;
  pos: Pos;
  home: Pos;
  state: RobotState;
  task_id: number | null;
  path: Pos[];
  distance: number;
  wait_ticks: number;
}

export interface SimTask {
  id: number;
  order_id: string;
  sku: string;
  quantity: number;
  shelf_id: number;
  access: Pos;
  pack_station: Pos;
  status: "queued" | "assigned" | "picked" | "delivered";
  robot_id: number | null;
}

export interface SimMetrics {
  tick: number;
  orders_total: number;
  orders_shipped: number;
  orders_in_progress: number;
  tasks_queued: number;
  avg_fulfillment_ticks: number | null;
  max_fulfillment_ticks: number | null;
  total_distance: number;
  total_wait_ticks: number;
  total_replans: number;
  utilization: number;
  throughput_per_100_ticks: number;
}

export type Scheduler = "fifo" | "nearest" | "batch_greedy";

export interface Snapshot {
  type: "snapshot";
  tick: number;
  scheduler: Scheduler;
  paused: boolean;
  tick_interval_ms: number;
  last_tick_ms: number;
  robots: Robot[];
  tasks: SimTask[];
  orders: Record<string, string>;
  metrics: SimMetrics;
}

export interface SimEvent {
  type: string;
  tick: number;
  order_id?: string;
  robot_id?: number;
  task_id?: number;
  [key: string]: unknown;
}

export interface PathResult {
  path: Pos[] | null;
  cost: number | null;
  expanded: number;
  visited: Pos[];
}

export type PathComparison = Record<"bfs" | "dijkstra" | "astar", PathResult>;

export interface StoreMetrics {
  store: {
    orders_by_status: Record<OrderStatus, number>;
    revenue_cents: number;
    units_in_stock: number;
  };
  simulation: SimMetrics | null;
}
