import { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  Position,
  useNodesState,
  type ReactFlowInstance,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { minutesOutline } from "../lib/mind-map";
export function MinutesMindMap({ title, content }: { title: string; content: string }) {
  const deferred = useDeferredValue(content);
  const [instance, setInstance] = useState<ReactFlowInstance | null>(null);
  const outline = useMemo(() => minutesOutline(title, deferred), [title, deferred]);
  const initialNodes = useMemo<Node[]>(
    () =>
      outline.map((point) => ({
        id: point.id,
        position: { x: point.x, y: point.y },
        data: { label: point.label },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        style: {
          width: 220,
          borderRadius: 12,
          padding: 14,
          fontSize: 12,
          lineHeight: 1.7,
          background: point.parent ? "var(--card)" : "var(--primary)",
          color: point.parent ? "var(--card-foreground)" : "var(--primary-foreground)",
          border: "1px solid var(--border)",
          whiteSpace: "normal" as const,
          overflowWrap: "anywhere" as const,
        },
      })),
    [outline],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  useEffect(() => {
    setNodes((current) => {
      const positions = new Map(current.map((node) => [node.id, node.position]));
      return initialNodes.map((node) => ({
        ...node,
        position: positions.get(node.id) ?? node.position,
      }));
    });
  }, [initialNodes, setNodes]);
  const edges = useMemo(
    () =>
      outline
        .filter((point) => point.parent)
        .map((point) => ({
          id: `edge-${point.id}`,
          source: point.parent!,
          target: point.id,
          type: "smoothstep",
          style: { stroke: "#94a3b8" },
        })),
    [outline],
  );
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      void instance?.fitView({ padding: 0.2, maxZoom: 1 });
    });
    return () => cancelAnimationFrame(frame);
  }, [instance, nodes.length]);
  return (
    <div className="relative h-full min-h-80 w-full" aria-label="会议重点思维导图">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onInit={setInstance}
        fitView
        nodesDraggable
        onNodesChange={onNodesChange}
        nodesConnectable={false}
        deleteKeyCode={null}
        minZoom={0.15}
        maxZoom={1.5}
      >
        <Background gap={20} size={1} color="#cbd5e1" />
        <Controls showInteractive={false} />
      </ReactFlow>
      {!content.trim() && (
        <p className="pointer-events-none absolute left-4 top-4 max-w-64 rounded-md bg-background/90 px-3 py-2 text-xs leading-5 text-muted-foreground">
          纪要有内容后，将按标题和条目展示重点结构。
        </p>
      )}
    </div>
  );
}
