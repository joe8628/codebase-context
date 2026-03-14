interface User {
  id: number;
  email: string;
}

type UserId = number;

class AuthService {
  login(email: string, password: string): Promise<User> {
    return Promise.resolve({ id: 1, email });
  }
}

function validateEmail(email: string): boolean {
  return email.includes("@");
}

const hashPassword = (password: string): string => {
  return password;
};
