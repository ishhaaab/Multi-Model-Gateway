import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useChatStore } from "@/stores/chat-store";
import { useChat } from "@/hooks/use-chat";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { MessageList } from "@/components/chat/MessageList";
import { ChatInput } from "@/components/chat/ChatInput";

export default function ChatPage() {
  const navigate = useNavigate();
  const { id: routeId } = useParams();

  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const messages = useChatStore((s) => s.messages);
  const loadingMessages = useChatStore((s) => s.loadingMessages);

  const { send, cancelStream, retryLast, isStreaming, streamedContent, streamError, pendingUserContent } =
    useChat();

  // URL → store. Guard against re-fetching the conversation we're already on
  // (which would wipe an in-flight stream right after auto-creation).
  useEffect(() => {
    const store = useChatStore.getState();
    if (routeId) {
      if (store.activeConversationId !== routeId) store.setActiveConversation(routeId);
    } else {
      store.startNewChat();
    }
  }, [routeId]);

  // store → URL. Reflect a freshly auto-created conversation in the address bar.
  useEffect(() => {
    if (activeConversationId && activeConversationId !== routeId) {
      navigate(`/chat/${activeConversationId}`, { replace: true });
    }
  }, [activeConversationId, routeId, navigate]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatHeader />
      <div className="min-h-0 flex-1">
        <MessageList
          messages={messages}
          loading={loadingMessages}
          pendingUserContent={pendingUserContent}
          streamedContent={streamedContent}
          isStreaming={isStreaming}
          streamError={streamError}
          onRetry={retryLast}
        />
      </div>
      <ChatInput onSend={(c) => send(c)} onCancel={cancelStream} isStreaming={isStreaming} />
    </div>
  );
}
