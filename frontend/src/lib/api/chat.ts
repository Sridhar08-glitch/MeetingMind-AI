import { api } from "./client";
import type {
  ApiSuccess,
  ChatConversation,
  ChatConversationDetail,
  ChatMessage,
  Paginated,
} from "@/lib/types";

export const chatApi = {
  async list(meetingId: string): Promise<ChatConversation[]> {
    const { data } = await api.get<Paginated<ChatConversation>>("/meetings/conversations/", {
      params: { meeting: meetingId, page_size: 100 },
    });
    return data.results;
  },

  async create(meetingId: string): Promise<ChatConversation> {
    const { data } = await api.post<ApiSuccess<ChatConversation>>("/meetings/conversations/", {
      meeting: meetingId,
    });
    return data.data;
  },

  async get(id: string): Promise<ChatConversationDetail> {
    const { data } = await api.get<ChatConversationDetail>(`/meetings/conversations/${id}/`);
    return data;
  },

  async ask(id: string, question: string): Promise<ChatMessage> {
    const { data } = await api.post<ApiSuccess<ChatMessage>>(
      `/meetings/conversations/${id}/ask/`, { question },
    );
    return data.data;
  },

  async rename(id: string, title: string): Promise<void> {
    await api.patch(`/meetings/conversations/${id}/`, { title });
  },

  async remove(id: string): Promise<void> {
    await api.delete(`/meetings/conversations/${id}/`);
  },

  async suggested(): Promise<string[]> {
    const { data } = await api.get<ApiSuccess<string[]>>("/meetings/chat/suggested/");
    return data.data;
  },
};
