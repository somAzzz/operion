"use client";

import { useMemo, useState, type ReactNode } from "react";
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
        const response = await fetch(`/api/conversations/${currentThreadId}`, {
          cache: "no-store",
        });
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
      },
      append: async () => {
        // The Agent API saves the completed run. Browser history is not authoritative.
      },
    }),
    [currentThreadId],
  );

  const threadListAdapter = useMemo(
    () => ({
      threadId: currentThreadId,
      onSwitchToNewThread: async () => {
        const newId = crypto.randomUUID();
        window.localStorage.setItem(THREAD_STORAGE_KEY, newId);
        setCurrentThreadId(newId);
      },
    }),
    [currentThreadId],
  );

  const runtime = useAgUiRuntime({
    agent,
    showThinking: false,
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
