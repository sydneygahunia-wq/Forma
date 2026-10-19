import type { Metadata } from "next";

import { PathfindingLab } from "@/components/pathfinding/pathfinding-lab";

export const metadata: Metadata = { title: "Pathfinding" };

export default function PathfindingPage() {
  return <PathfindingLab />;
}
