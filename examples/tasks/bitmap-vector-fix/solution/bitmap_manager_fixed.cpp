//
// Oracle fixed version of bitmap_manager.cpp
// Bug fixes applied:
//   1. grow(): reserve() → resize(), so operator[] is valid after growth
//   2. grow(): loop goes from old_bit_depth upward (avoids size_t underflow)
//   3. addBitMap(): pass old_bit_depth + values.size() to grow() (not just values.size())
//   4. addBitMap()/loadBitMap(): cast hash result to int consistently via basis_hash_string
//
#include "bitmap_manager.h"

std::vector<std::string> BitMapManager::split(const std::string& s, char delim) {
    std::vector<std::string> out;
    size_t start = 0;
    size_t pos;
    while ((pos = s.find(delim, start)) != std::string::npos) {
        out.push_back(s.substr(start, pos - start));
        start = pos + 1;
    }
    out.push_back(s.substr(start));
    return out;
}

size_t BitMapManager::basis_hash_string(const std::string& s) {
    size_t h = 0;
    for (const char c : s) {
        h = h * 131 + c;
    }
    return h;
}

void BitMapManager::grow(size_t new_bit_depth) {
    size_t old_bit_depth = index_bitmap_vec_.size();
    if (old_bit_depth >= new_bit_depth) {
        return;
    }
    // FIX 1: resize() instead of reserve() — ensures operator[] is valid
    index_bitmap_vec_.resize(new_bit_depth);
    // FIX 2: iterate from old_bit_depth upward, not downward
    for (size_t i = old_bit_depth; i < new_bit_depth; i++) {
        index_bitmap_vec_[i] = new BitMap();
    }
}

void BitMapManager::addBitMap(const std::vector<std::string>& values,
                               const std::vector<std::string>& tags) {
    size_t old_bit_depth = index_bitmap_vec_.size();
    // FIX 3: target size is old + new, not just new
    grow(old_bit_depth + values.size());
    for (size_t i = 0; i < values.size(); i++) {
        index_bitmap_desc_.push_back(tags[i]);
        const std::vector<std::string> bitmaps = split(values[i], '\n');
        for (size_t j = 0; j < bitmaps.size(); j++) {
            index_bitmap_vec_[old_bit_depth + i]->v.push_back(
                static_cast<int>(basis_hash_string(bitmaps[j])));
        }
    }
}

bool BitMapManager::exists(const std::vector<std::pair<std::string, int>>& values) {
    for (size_t i = 0; i < values.size(); i++) {
        const std::pair<std::string, int>& v = values[i];
        if (static_cast<size_t>(v.second) >= index_bitmap_vec_.size()) {
            return false;
        }
        if (!index_bitmap_vec_[v.second]->exists(
                static_cast<int>(basis_hash_string(v.first)))) {
            return false;
        }
    }
    return true;
}

void BitMapManager::loadBitMap(const std::string& values) {
    index_bitmap_vec_.push_back(new BitMap());
    index_bitmap_desc_.push_back("primary_key");
    const std::vector<std::string> bitmaps = split(values, '\n');
    for (size_t i = 0; i < bitmaps.size(); i++) {
        index_bitmap_vec_[0]->v.push_back(
            static_cast<int>(basis_hash_string(bitmaps[i])));
    }
}
