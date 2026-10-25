import type { JWK } from "jose";

export type AuthUser = {
  id: number;
  username: string;
  department: string;
  role: string;
  status: number;
  created_at: string;
  updated_at: string;
};

export type AuthSession = { token: string; user: AuthUser };

export type AuthMode = "login" | "register";
export type CredentialErrors = Partial<Record<"username" | "password", string>>;

export type PasswordEncryptionKey = {
  key_id: string;
  algorithm: string;
  encryption: string;
  public_key: JWK;
  server_time: number;
};
