import { supabase } from "../supabaseClient";

function getConversationPairs(messages = []) {
  const pairs = [];

  for (let index = 0; index < messages.length; index += 1) {
    const current = messages[index];
    const next = messages[index + 1];

    if (current?.role === "user" && next?.role === "assistant") {
      pairs.push({
        question: current.content,
        answer: next.content,
      });
      index += 1;
    }
  }

  return pairs;
}

export async function logChatActivity({ user, question, answer, conversationId }) {
  if (!user || !question?.trim() || !answer?.trim()) {
    return;
  }

  const payload = {
    user_id: user.id,
    user_email: user.email ?? null,
    question,
    answer,
  };

  const { error } = await supabase.from("chat_logs").insert({
    ...payload,
    conversation_id: conversationId ?? null,
  });

  if (!error) return;

  const isMissingConversationIdColumn =
    error.code === "PGRST204" ||
    error.message?.toLowerCase().includes("conversation_id");

  if (isMissingConversationIdColumn) {
    const { error: retryError } = await supabase.from("chat_logs").insert(payload);

    if (!retryError) return;
  }

  if (error) {
    // Avoid breaking chat flow if analytics storage is not configured yet.
    console.warn("Failed to store chat analytics:", error.message);
  }
}

export async function deleteChatActivity({ user, conversation }) {
  if (!user?.id || !conversation?.id) {
    return;
  }

  const { error } = await supabase
    .from("chat_logs")
    .delete()
    .eq("user_id", user.id)
    .eq("conversation_id", conversation.id);

  if (!error) return;

  const isMissingConversationIdColumn =
    error.code === "42703" ||
    error.code === "PGRST204" ||
    error.message?.toLowerCase().includes("conversation_id");

  if (!isMissingConversationIdColumn) {
    console.warn("Failed to delete chat analytics:", error.message);
    return;
  }

  const pairs = getConversationPairs(conversation.messages);

  await Promise.all(
    pairs.map(async ({ question, answer }) => {
      const { error: pairError } = await supabase
        .from("chat_logs")
        .delete()
        .eq("user_id", user.id)
        .eq("question", question)
        .eq("answer", answer);

      if (pairError) {
        console.warn("Failed to delete chat analytics row:", pairError.message);
      }
    }),
  );
}
