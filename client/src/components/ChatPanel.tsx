import { useState, useRef, useEffect, useCallback, useImperativeHandle, forwardRef } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface ChatPanelHandle {
  sendQuery: (text: string) => void;
}

interface Props {
  boroughs: string[];
  onBoroughSelect: (borough: string) => void;
  selectedBorough: string | null;
}

const GENERIC_CHIPS = [
  { label: "Pires zones", prompt: "Quelles sont les pires zones sous-desservies a Montreal?" },
  { label: "Vue d'ensemble", prompt: "Donne-moi un apercu de l'accessibilite des services a Montreal" },
  { label: "Comparer arrondissements", prompt: "Compare les 3 pires et 3 meilleurs arrondissements" },
  { label: "Estimer couts Montreal-Nord", prompt: "Estimate project cost to fix gaps in MONTREAL-NORD" },
];

function boroughChips(borough: string) {
  return [
    { label: "Que manque-t-il?", prompt: `Quels services manquent dans ${borough}?` },
    { label: "Lacunes transit", prompt: `Analyse les lacunes de transport en commun dans ${borough}` },
    { label: "Estimer couts", prompt: `Estimate project cost to fix gaps in ${borough}` },
    { label: "Besoins infra", prompt: `Flag infrastructure needs for ${borough}` },
    { label: "Croissance +15%", prompt: `Simulate 15% population growth in ${borough}` },
  ];
}

export const ChatPanel = forwardRef<ChatPanelHandle, Props>(function ChatPanel(
  { boroughs, onBoroughSelect, selectedBorough },
  ref
) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Welcome! I audit Montreal's 15-minute city readiness.\n\nTry:\n- **Score [borough]** \u2014 e.g., \"Score Montreal-Nord\"\n- **Find deserts** \u2014 identify underserved areas\n- **Compare** two boroughs\n\nSelect a borough above to see its map overlay.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [summarize, setSummarize] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const [streamStatus, setStreamStatus] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text || loading) return;

      setMessages((prev) => [...prev, { role: "user", content: text }]);
      setLoading(true);
      setStreamStatus("Connexion...");

      const lowerText = text.toLowerCase();
      for (const b of boroughs) {
        if (lowerText.includes(b.toLowerCase())) {
          onBoroughSelect(b);
          break;
        }
      }

      try {
        const history = messages
          .slice(1)
          .map((m) => ({ role: m.role, content: m.content }));

        const res = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, history, summarize }),
        });

        if (!res.ok || !res.body) {
          throw new Error("Stream failed");
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalContent = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === "status") {
                setStreamStatus(event.content);
              } else if (event.type === "tool_call") {
                setStreamStatus(`Appel ${event.tool}...`);
              } else if (event.type === "tool_result") {
                setStreamStatus(`Resultats de ${event.tool}`);
              } else if (event.type === "done") {
                finalContent = event.content;
              } else if (event.type === "error") {
                finalContent = `Error: ${event.content}`;
              }
            } catch {
              // skip malformed lines
            }
          }
        }

        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: finalContent || "No response received." },
        ]);
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Error connecting to the analysis engine. Please try again.",
          },
        ]);
      } finally {
        setLoading(false);
        setStreamStatus(null);
      }
    },
    [loading, messages, boroughs, onBoroughSelect, summarize]
  );

  useImperativeHandle(
    ref,
    () => ({
      sendQuery: (text: string) => sendMessage(text),
    }),
    [sendMessage]
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    sendMessage(text);
  }

  const chips = selectedBorough ? boroughChips(selectedBorough) : GENERIC_CHIPS;

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div>
          <span style={{ marginRight: "0.4rem" }}>{"\u{1F916}"}</span>
          Agent de planification
        </div>
        <label className="detail-check">
          <input
            type="checkbox"
            checked={!summarize}
            onChange={() => setSummarize((v) => !v)}
          />
          Detaille
        </label>
      </div>
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`chat-msg ${msg.role}`}
            dangerouslySetInnerHTML={{ __html: simpleMarkdown(msg.content) }}
          />
        ))}
        {loading && (
          <div className="chat-msg assistant">
            <div className="step-indicator">
              <div className="step-dots">
                <div className="step-dot" />
                <div className="step-dot" />
                <div className="step-dot" />
              </div>
              <span>{streamStatus || "Analyse..."}</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-chips">
        {chips.map((chip) => (
          <button
            key={chip.label}
            className="chat-chip"
            onClick={() => sendMessage(chip.prompt)}
            disabled={loading}
          >
            {chip.label}
          </button>
        ))}
      </div>

      <form className="chat-input-area" onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Posez une question sur l'equite urbaine..."
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          Envoyer
        </button>
      </form>
    </div>
  );
});

function simpleMarkdown(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^### (.+)$/gm, "<h3 style='font-size:0.8rem;margin:0.25rem 0'>$1</h3>")
    .replace(/^- (.+)$/gm, "\u2022 $1")
    .replace(/\n/g, "<br />");
}
