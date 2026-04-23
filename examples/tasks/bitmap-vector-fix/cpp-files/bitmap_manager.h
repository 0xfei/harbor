//
// Created by 0x01f on 2026/4/23.
//

#ifndef BITMAP_MANAGER_H
#define BITMAP_MANAGER_H

#include <vector>
#include "hash.h"
#include "bitmap.h"

class BitMapManager {
public:
    BitMapManager() = default;
    ~BitMapManager() = default;
    void loadBitMap(const std::string& values);
    void addBitMap(const std::vector<std::string>& values, const std::vector<std::string>& tags);

    bool exists(const std::vector<std::pair<std::string, int>>& values);
    size_t size() const {
        return index_bitmap_vec_.size();
    }

private:
    static std::vector<std::string> split(const std::string& s, char delim);
    static size_t basis_hash_string(const std::string& s);

    void grow(size_t new_bit_depth);

    std::vector<BitMap*> index_bitmap_vec_;
    std::vector<std::string> index_bitmap_desc_;
};

#endif //BITMAP_MANAGER_H
