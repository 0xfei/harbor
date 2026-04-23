//
// Created by 0x01f on 2026/4/23.
//

#ifndef BITMAP_H

struct BitMap {
    std::vector<int> v{};

    bool exists(int k) {
        for (auto i : v) {
            if (i == k) {
                return true;
            }
        }
        return false;
    }
};

#define BITMAP_H

#endif //BITMAP_H
