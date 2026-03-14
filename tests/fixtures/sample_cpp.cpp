#include <string>

class AuthService {
public:
    bool login(const std::string& email, const std::string& password) {
        return validate_email(email);
    }

    bool logout(const std::string& token) {
        return true;
    }
};

bool validate_email(const std::string& email) {
    return email.find('@') != std::string::npos;
}

std::string hash_password(const std::string& password) {
    return password;
}
