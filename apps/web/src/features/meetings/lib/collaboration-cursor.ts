export function collaboratorInitials(name: string) {
  return Array.from(name.trim()).slice(0, 2).join("").toUpperCase() || "?";
}

/** 按账号分散色相，避免少量固定颜色反复撞色。 */
export function collaboratorColor(identity: string | number) {
  let hash = typeof identity === "number" ? identity : 0;
  if (typeof identity === "string")
    for (const character of identity) hash = (hash * 31 + character.codePointAt(0)!) >>> 0;
  const hue = (((hash * 137.508) % 360) + 360) % 360;
  const saturation = 0.68;
  const lightness = 0.36;
  const amplitude = saturation * Math.min(lightness, 1 - lightness);
  const channel = (offset: number) => {
    const k = (offset + hue / 30) % 12;
    const value = lightness - amplitude * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(255 * value)
      .toString(16)
      .padStart(2, "0");
  };
  return `#${channel(0)}${channel(8)}${channel(4)}`;
}

/** 光标装饰由编辑器管理生命周期，使用安全的文本节点展示用户头像。 */
export function renderCollaborationCursor(user: { name: string; color: string }) {
  const root = document.createElement("span");
  root.className = "bn-collaboration-cursor__base";
  root.contentEditable = "false";
  const caret = document.createElement("span");
  caret.className = "bn-collaboration-cursor__caret";
  const color = /^#[0-9a-f]{6}$/i.test(user.color) ? user.color : collaboratorColor(user.name);
  caret.style.backgroundColor = color;
  const avatar = document.createElement("span");
  avatar.className = "meeting-collaboration-cursor-avatar";
  avatar.dataset.slot = "avatar";
  avatar.title = user.name;
  avatar.setAttribute("aria-label", `${user.name}的光标`);
  avatar.setAttribute("role", "img");
  avatar.style.backgroundColor = color;
  avatar.textContent = collaboratorInitials(user.name);
  caret.append(avatar);
  root.append(document.createTextNode("\u2060"), caret, document.createTextNode("\u2060"));
  return root;
}
