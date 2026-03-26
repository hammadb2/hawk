import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  CRMUser,
  Prospect,
  Client,
  Notification,
  PipelineStage,
} from "@/types/crm";

interface CRMStore {
  // ─── User ────────────────────────────────────────────────────────────────────
  user: CRMUser | null;
  setUser: (user: CRMUser | null) => void;

  // ─── Prospects ───────────────────────────────────────────────────────────────
  prospects: Prospect[];
  setProspects: (prospects: Prospect[]) => void;
  updateProspect: (id: string, updates: Partial<Prospect>) => void;
  moveProspect: (id: string, stage: PipelineStage) => void;
  addProspect: (prospect: Prospect) => void;
  removeProspect: (id: string) => void;

  // ─── Clients ─────────────────────────────────────────────────────────────────
  clients: Client[];
  setClients: (clients: Client[]) => void;
  updateClient: (id: string, updates: Partial<Client>) => void;
  addClient: (client: Client) => void;

  // ─── Notifications ───────────────────────────────────────────────────────────
  notifications: Notification[];
  setNotifications: (notifications: Notification[]) => void;
  addNotification: (notification: Notification) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;

  // ─── UI State ────────────────────────────────────────────────────────────────
  selectedProspect: Prospect | null;
  setSelectedProspect: (prospect: Prospect | null) => void;
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  globalSearch: string;
  setGlobalSearch: (search: string) => void;

  // ─── Pipeline View ───────────────────────────────────────────────────────────
  pipelineView: "kanban" | "list" | "table";
  setPipelineView: (view: "kanban" | "list" | "table") => void;

  // ─── Filters ─────────────────────────────────────────────────────────────────
  pipelineFilters: {
    rep?: string;
    industry?: string;
    city?: string;
    stage?: string;
    source?: string;
    scoreMin?: number;
    scoreMax?: number;
    dateFrom?: string;
    dateTo?: string;
  };
  setPipelineFilters: (filters: CRMStore["pipelineFilters"]) => void;
  clearPipelineFilters: () => void;
}

export const useCRMStore = create<CRMStore>()(
  persist(
    (set) => ({
      // ─── User ──────────────────────────────────────────────────────────────────
      user: null,
      setUser: (user) => set({ user }),

      // ─── Prospects ─────────────────────────────────────────────────────────────
      prospects: [],
      setProspects: (prospects) => set({ prospects }),
      updateProspect: (id, updates) =>
        set((state) => ({
          prospects: state.prospects.map((p) =>
            p.id === id ? { ...p, ...updates } : p
          ),
        })),
      moveProspect: (id, stage) =>
        set((state) => ({
          prospects: state.prospects.map((p) =>
            p.id === id ? { ...p, stage } : p
          ),
        })),
      addProspect: (prospect) =>
        set((state) => ({ prospects: [prospect, ...state.prospects] })),
      removeProspect: (id) =>
        set((state) => ({
          prospects: state.prospects.filter((p) => p.id !== id),
        })),

      // ─── Clients ───────────────────────────────────────────────────────────────
      clients: [],
      setClients: (clients) => set({ clients }),
      updateClient: (id, updates) =>
        set((state) => ({
          clients: state.clients.map((c) =>
            c.id === id ? { ...c, ...updates } : c
          ),
        })),
      addClient: (client) =>
        set((state) => ({ clients: [client, ...state.clients] })),

      // ─── Notifications ─────────────────────────────────────────────────────────
      notifications: [],
      setNotifications: (notifications) => set({ notifications }),
      addNotification: (notification) =>
        set((state) => ({
          notifications: [notification, ...state.notifications],
        })),
      markRead: (id) =>
        set((state) => ({
          notifications: state.notifications.map((n) =>
            n.id === id ? { ...n, read: true } : n
          ),
        })),
      markAllRead: () =>
        set((state) => ({
          notifications: state.notifications.map((n) => ({ ...n, read: true })),
        })),

      // ─── UI State ──────────────────────────────────────────────────────────────
      selectedProspect: null,
      setSelectedProspect: (prospect) => set({ selectedProspect: prospect }),
      drawerOpen: false,
      setDrawerOpen: (open) => set({ drawerOpen: open }),
      sidebarCollapsed: false,
      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      globalSearch: "",
      setGlobalSearch: (search) => set({ globalSearch: search }),

      // ─── Pipeline View ─────────────────────────────────────────────────────────
      pipelineView: "kanban",
      setPipelineView: (view) => set({ pipelineView: view }),

      // ─── Filters ───────────────────────────────────────────────────────────────
      pipelineFilters: {},
      setPipelineFilters: (filters) => set({ pipelineFilters: filters }),
      clearPipelineFilters: () => set({ pipelineFilters: {} }),
    }),
    {
      name: "hawk-crm-store",
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        pipelineView: state.pipelineView,
      }),
    }
  )
);
