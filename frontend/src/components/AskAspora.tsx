import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { MessageCircle, Send, Sparkles, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatResponse {
  available: boolean;
  reply: string;
  tool_calls: number;
}

const SUGGESTED_PROMPTS = [
  "What's overdue right now?",
  "Summarise what's due this week.",
  "Which entity has the most open obligations?",
  "Show me all GST/VAT filings due in the next 30 days.",
];

export function AskAspora() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const chatMutation = useMutation({
    mutationFn: (history: Message[]) =>
      api.post<ChatResponse>("/api/chat", { messages: history }),
    onSuccess: (data) => {
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
    },
  });

  function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || chatMutation.isPending) return;
    const next: Message[] = [...messages, { role: "user", content: trimmed }];
    setMessages(next);
    setInput("");
    chatMutation.mutate(next);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    send(input);
  }

  // Autoscroll on new messages or while waiting.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length, chatMutation.isPending]);

  useEffect(() => {
    if (open && inputRef.current) {
      const t = setTimeout(() => inputRef.current?.focus(), 100);
      return () => clearTimeout(t);
    }
  }, [open]);

  return (
    <>
      {/* Floating launcher */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full bg-aspora-600 text-white px-4 py-3 shadow-lg shadow-aspora-600/30 hover:bg-aspora-700 transition-colors"
          aria-label="Open Ask Aspora"
        >
          <Sparkles className="h-5 w-5" />
          <span className="text-sm font-medium">Ask Aspora</span>
        </button>
      )}

      {/* Panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 flex flex-col w-[420px] max-w-[calc(100vw-3rem)] h-[600px] max-h-[calc(100vh-3rem)] rounded-2xl border border-border bg-background shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-gradient-to-r from-aspora-600 to-aspora-700 text-white rounded-t-2xl">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-lg bg-white/15 grid place-items-center">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <div className="text-sm font-semibold">Ask Aspora</div>
                <div className="text-[11px] opacity-80">Your compliance copilot</div>
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="p-1.5 rounded-md hover:bg-white/15"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Messages */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin"
          >
            {messages.length === 0 && !chatMutation.isPending && (
              <div className="space-y-3">
                <div className="text-sm text-muted-foreground">
                  Hi — I can read your compliance data and answer questions about it.
                  Some ideas to start:
                </div>
                <div className="grid gap-2">
                  {SUGGESTED_PROMPTS.map((p) => (
                    <button
                      key={p}
                      onClick={() => send(p)}
                      className="text-left rounded-lg border border-border px-3 py-2 text-sm hover:bg-secondary/50 transition-colors"
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <Bubble key={i} role={m.role} content={m.content} />
            ))}

            {chatMutation.isPending && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin text-aspora-600" />
                <span>Looking it up…</span>
              </div>
            )}

            {chatMutation.error && (
              <Bubble
                role="assistant"
                content={`Error: ${(chatMutation.error as Error).message}`}
                isError
              />
            )}
          </div>

          {/* Input */}
          <form
            onSubmit={handleSubmit}
            className="flex items-center gap-2 p-3 border-t border-border"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything about your obligations…"
              className="flex-1 h-10 rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <Button
              type="submit"
              size="icon"
              disabled={!input.trim() || chatMutation.isPending}
            >
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </div>
      )}
    </>
  );
}

function Bubble({
  role,
  content,
  isError,
}: {
  role: "user" | "assistant";
  content: string;
  isError?: boolean;
}) {
  const isUser = role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap",
          isUser
            ? "bg-aspora-600 text-white"
            : isError
              ? "bg-destructive/10 border border-destructive/30 text-destructive"
              : "bg-secondary text-foreground",
        )}
      >
        {content}
      </div>
    </div>
  );
}
