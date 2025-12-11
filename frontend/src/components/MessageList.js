import MessageBubble from "./MessageBubble";

export default function MessageList({ messages, streamingAnswer }) {
  return (
    <div>
      {messages.map((msg, idx) => (
        <MessageBubble key={msg.id || idx} message={msg} />
      ))}
      {streamingAnswer && (
        <MessageBubble
          message={{ role: "assistant", content: streamingAnswer, streaming: true }}
        />
      )}
    </div>
  );
}
