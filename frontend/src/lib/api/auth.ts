import { api } from "./client";
import type { ApiSuccess, LoginResponse, User } from "@/lib/types";

export interface RegisterPayload {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

export const authApi = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const { data } = await api.post<LoginResponse>("/auth/login/", { email, password });
    return data;
  },

  async register(payload: RegisterPayload): Promise<User> {
    const { data } = await api.post<ApiSuccess<User>>("/auth/register/", payload);
    return data.data;
  },

  async logout(refresh: string): Promise<void> {
    await api.post("/auth/logout/", { refresh });
  },

  async profile(): Promise<User> {
    const { data } = await api.get<ApiSuccess<User>>("/auth/profile/");
    return data.data;
  },

  async updateProfile(payload: { first_name?: string; last_name?: string }): Promise<User> {
    const { data } = await api.patch<ApiSuccess<User>>("/auth/profile/", payload);
    return data.data;
  },

  async changePassword(payload: { current_password: string; new_password: string }): Promise<void> {
    await api.post("/auth/change-password/", payload);
  },

  async forgotPassword(email: string): Promise<void> {
    await api.post("/auth/forgot-password/", { email });
  },

  async resetPassword(token: string, new_password: string): Promise<void> {
    await api.post("/auth/reset-password/", { token, new_password });
  },
};
