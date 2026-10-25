export type OutlinePoint = {
  id: string;
  parent: string | null;
  label: string;
  depth: number;
  x: number;
  y: number;
};
/** 按纪要标题和条目构建结构导图，不添加原文中不存在的重点。 */
export function minutesOutline(title: string, markdown: string): OutlinePoint[] {
  const points: OutlinePoint[] = [
    { id: "root", parent: null, label: title.slice(0, 180), depth: 0, x: 0, y: 0 },
  ];
  const headings: { level: number; id: string }[] = [];
  let fenced = false;
  for (const line of markdown.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) {
      fenced = !fenced;
      continue;
    }
    if (fenced || points.length >= 120) continue;
    const value = line.trim();
    if (!value || /^([-*_])\1{2,}$/.test(value)) continue;
    const heading = /^(#{1,6})\s+(.+)$/.exec(value);
    if (heading) {
      const level = heading[1].length;
      while (headings.length && headings.at(-1)!.level >= level) headings.pop();
      const parent = headings.at(-1)?.id ?? "root";
      const label = heading[2].replace(/[*_`]/g, "").trim();
      if (level === 1 && label === title) continue;
      const id = `point-${points.length}`;
      const depth = (points.find((point) => point.id === parent)?.depth ?? 0) + 1;
      points.push({ id, parent, label, depth, x: depth * 280, y: 0 });
      headings.push({ level, id });
    } else {
      const parent = headings.at(-1)?.id ?? "root";
      const label = value
        .replace(/^(?:[-*+]\s+(?:\[[ xX]\]\s*)?|\d+[.)]\s+|>\s*)/, "")
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
        .replace(/[*_`]/g, "")
        .trim();
      if (!label) continue;
      const depth = (points.find((point) => point.id === parent)?.depth ?? 0) + 1;
      points.push({
        id: `point-${points.length}`,
        parent,
        label: label.slice(0, 180),
        depth,
        x: depth * 280,
        y: 0,
      });
    }
  }
  let row = 0;
  function position(point: OutlinePoint) {
    const children = points.filter((item) => item.parent === point.id);
    if (!children.length) {
      point.y = row;
      row += Math.max(100, Math.ceil(point.label.length / 25) * 20 + 40);
      return;
    }
    children.forEach(position);
    point.y = (children[0].y + children.at(-1)!.y) / 2;
  }
  position(points[0]);
  return points;
}
