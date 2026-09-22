"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  AssistantRuntimeProvider,
  ExportedMessageRepository,
} from "@assistant-ui/react";
import { HttpAgent } from "@ag-ui/client";
import {
  fromAgUiMessages,
  useAgUiRuntime,
} from "@assistant-ui/react-ag-ui";

const THREAD_STORAGE_KEY = "operion.active-thread";

type ConversationSummary = {
  conversation_id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
};

function initialThreadId() {
  if (typeof window === "undefined") return "operion-new-thread";
  const stored = window.localStorage.getItem(THREAD_STORAGE_KEY);
  if (stored) return stored;
  const created = crypto.randomUUID();
  window.localStorage.setItem(THREAD_STORAGE_KEY, created);
  return created;
}

/**
 * AG-UI runtime with threadList adapter for multi-thread support.
 */
export function MyRuntimeProvider({
  children,
}: Readonly<{ children: ReactNode }>) {
  const [currentThreadId, setCurrentThreadId] = useState(initialThreadId);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);

  const fetchHistory = useCallback(async (threadId: string) => {
    const response = await fetch(
      `/api/conversations/${encodeURIComponent(threadId)}`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      if (response.status === 404) {
        return ExportedMessageRepository.fromArray([]);
      }
      throw new Error("Unable to restore the trusted conversation history.");
    }
    const data = (await response.json()) as { messages: readonly unknown[] };
    return ExportedMessageRepository.fromArray(
      fromAgUiMessages(data.messages, { showThinking: false }),
    );
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const response = await fetch("/api/conversations", { cache: "no-store" });
      if (!response.ok) throw new Error("Unable to list conversations.");
      const data = (await response.json()) as {
        conversations: ConversationSummary[];
      };
      setConversations(data.conversations);
    } catch {
      setConversations([]);
    } finally {
      setIsLoadingConversations(false);
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  const agent = useMemo(() => {
    return new HttpAgent({
      url: "/api/agent",
      threadId: currentThreadId,
      headers: {
        Accept: "text/event-stream",
      },
    });
  }, [currentThreadId]);

  const historyAdapter = useMemo(
    () => ({
      load: async () => {
        return fetchHistory(currentThreadId);
      },
      append: async () => {
        // The Agent API remains authoritative; this only refreshes its index.
        await refreshConversations();
      },
    }),
    [currentThreadId, fetchHistory, refreshConversations],
  );

  const threadListAdapter = useMemo(
    () => ({
      threadId: currentThreadId,
      isLoading: isLoadingConversations,
      threads: conversations.map((conversation) => ({
        status: "regular" as const,
        id: conversation.conversation_id,
        remoteId: conversation.conversation_id,
        title: conversation.title,
        custom: {
          messageCount: conversation.message_count,
          updatedAt: conversation.updated_at,
        },
      })),
      onSwitchToNewThread: async () => {
        const newId = crypto.randomUUID();
        window.localStorage.setItem(THREAD_STORAGE_KEY, newId);
        setCurrentThreadId(newId);
      },
      onSwitchToThread: async (threadId: string) => {
        const history = await fetchHistory(threadId);
        window.localStorage.setItem(THREAD_STORAGE_KEY, threadId);
        setCurrentThreadId(threadId);
        return { messages: history.messages.map((item) => item.message) };
      },
      onDelete: async (threadId: string) => {
        const response = await fetch(
          `/api/conversations/${encodeURIComponent(threadId)}`,
          {
            method: "DELETE",
            headers: { "X-Operion-Intent": "delete-conversation" },
          },
        );
        if (!response.ok) {
          throw new Error("Unable to delete the conversation.");
        }
        setConversations((current) =>
          current.filter(
            (conversation) => conversation.conversation_id !== threadId,
          ),
        );
        if (threadId === currentThreadId) {
          const newId = crypto.randomUUID();
          window.localStorage.setItem(THREAD_STORAGE_KEY, newId);
          setCurrentThreadId(newId);
        }
      },
    }),
    [conversations, currentThreadId, fetchHistory, isLoadingConversations],
  );

  const runtime = useAgUiRuntime({
    agent,
    showThinking: false,
    // Keep the composer usable while a response is in flight. A follow-up is
    // queued and released only after the active run reaches a terminal state,
    // so transient stream delays cannot make the interface feel locked.
    unstable_enableMessageQueue: true,
    adapters: {
      history: historyAdapter,
      threadList: threadListAdapter,
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
