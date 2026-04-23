//
// Created by 0x01f on 2026/4/23.
//

#ifndef HASH_H

#include <string>

inline long hash_compile_time(const std::string& s) {
    long h = 0;
    for (const char c : s) {
        h = h * 131 + c;
    }
    return h;
}

#define STR2BITMAP(s) hash_compile_time(s)

#define HASH_H

#endif //HASH_H
