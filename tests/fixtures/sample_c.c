#include <stdio.h>
#include <string.h>

struct UserService {
    int user_count;
};

int validate_email(const char *email) {
    return strchr(email, '@') != NULL;
}

int validate_password(const char *password) {
    return strlen(password) >= 8;
}
