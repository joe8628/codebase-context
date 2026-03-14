import { User, UserId } from "../types/user";

export class AuthService {
  async login(email: string, password: string): Promise<User> {
    return { id: 1, email, createdAt: new Date() };
  }

  async logout(userId: UserId): Promise<void> {
    return;
  }
}
