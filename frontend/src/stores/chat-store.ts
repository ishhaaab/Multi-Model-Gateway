import { create } from "zustand";
import { convoApi } from "@/lib/api-endpoints";
import type { Conversation, Message, Provider } from "@/lib/types";

function sortConversations(list: Conversation[]): Conversation[] {
  return [...list].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}

// Backend does not order messages, and a user+assistant turn shares one `index`.
// Order by index, then put the user message before the assistant within a turn.
function sortMessages(list: Message[]): Message[] {
  const roleRank = (r: string) => (r === "system" ? 0 : r === "user" ? 1 : 2);
  return [...list].sort((a, b) => {
    const ai = a.index ?? 0;
    const bi = b.index ?? 0;
    if (ai !== bi) return ai - bi;
    const rr = roleRank(a.role) - roleRank(b.role);
    if (rr !== 0) return rr;
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });
}

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  messages: Message[];
  isStreaming: boolean;
  streamedContent: string;
  streamError: string | null;
  loadingConversations: boolean;
  loadingMessages: boolean;

  // Compose selections shared by header + input bar
  provider: Provider;
  presetId: string | null;
  isPrivate: boolean;

  fetchConversations: () => Promise<void>;
  createConversation: (title: string) => Promise<string>;
  setActiveConversation: (id: string | null) => void;
  startNewChat: () => void;
  fetchMessages: (id: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;

  appendToStream: (content: string) => void;
  setStreaming: (streaming: boolean) => void;
  clearStream: () => void;
  setStreamError: (err: string | null) => void;

  setProvider: (p: Provider) => void;
  setPresetId: (id: string | null) => void;
  setPrivate: (v: boolean) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: [],
  isStreaming: false,
  streamedContent: "",
  streamError: null,
  loadingConversations: false,
  loadingMessages: false,

  provider: "auto",
  presetId: null,
  isPrivate: false,

  fetchConversations: async () => {
    set({ loadingConversations: true });
    try {
      const convos = await convoApi.list();
      set({ conversations: sortConversations(convos) });
    } finally {
      set({ loadingConversations: false });
    }
  },

  createConversation: async (title) => {
    const { id } = await convoApi.create(title);
    set({ activeConversationId: id, messages: [], streamError: null });
    // Refresh list so the new conversation appears with its metadata.
    get().fetchConversations();
    return id;
  },

  setActiveConversation: (id) => {
    set({ activeConversationId: id, streamError: null });
    if (id) {
      get().fetchMessages(id);
    } else {
      set({ messages: [] });
    }
  },

  startNewChat: () => {
    set({ activeConversationId: null, messages: [], streamError: null, streamedContent: "" });
  },

  fetchMessages: async (id) => {
    set({ loadingMessages: true });
    try {
      const messages = await convoApi.getMessages(id);
      set({ messages: sortMessages(messages) });
    } finally {
      set({ loadingMessages: false });
    }
  },

  renameConversation: async (id, title) => {
    await convoApi.rename(id, title);
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, title } : c
      ),
    }));
  },

  deleteConversation: async (id) => {
    await convoApi.delete(id);
    set((state) => {
      const wasActive = state.activeConversationId === id;
      return {
        conversations: state.conversations.filter((c) => c.id !== id),
        activeConversationId: wasActive ? null : state.activeConversationId,
        messages: wasActive ? [] : state.messages,
      };
    });
  },

  appendToStream: (content) =>
    set((state) => ({ streamedContent: state.streamedContent + content })),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  clearStream: () => set({ streamedContent: "", streamError: null }),

  setStreamError: (err) => set({ streamError: err }),

  setProvider: (p) => set({ provider: p }),
  setPresetId: (id) => set({ presetId: id }),
  setPrivate: (v) => set({ isPrivate: v }),
}));
