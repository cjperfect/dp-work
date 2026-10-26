import { create } from "zustand";
import type { AppStore } from "@/interfaces/app";

export const useAppStore = create<AppStore>((set) => ({
  view: "agent",
  agentId: "general",
  enabledKbs: [],
  currentModel: "",
  meetingTitle: null,
  meetingStatus: "live",
  threadAgent: {},
  setView: (view) => set({ view }),
  setAgentId: (agentId) => set({ agentId }),
  toggleKb: (id) =>
    set((state) => ({
      enabledKbs: state.enabledKbs.includes(id)
        ? state.enabledKbs.filter((kbId) => kbId !== id)
        : [...state.enabledKbs, id],
    })),
  setModel: (currentModel) => set({ currentModel }),
  setMeetingTitle: (meetingTitle) => set({ meetingTitle }),
  setMeetingStatus: (meetingStatus) => set({ meetingStatus }),
  bindThreadAgent: (threadId, agentId) =>
    set((state) => {
      if (!threadId || state.threadAgent[threadId]) return state;
      return { threadAgent: { ...state.threadAgent, [threadId]: agentId } };
    }),
}));
