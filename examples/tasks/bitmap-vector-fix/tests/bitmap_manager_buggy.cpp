//
// Created by 0x01f on 2026/4/23.
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
    index_bitmap_vec_.reserve(new_bit_depth);
    for (size_t i = new_bit_depth - 1; i >= old_bit_depth; i--) {
        index_bitmap_vec_[i] = new BitMap();
    }
}

void BitMapManager::addBitMap(const std::vector<std::string>& values, const std::vector<std::string>& tags) {
    size_t old_bit_depth = index_bitmap_vec_.size();
    grow(values.size());
    for (size_t i = 0; i < values.size(); i++) {
        index_bitmap_desc_.push_back(tags[i]);
        const std::vector<std::string> bitmaps = split(values[i], '\n');
        for (size_t j = 0; j < bitmaps.size(); j++) {
            index_bitmap_vec_[old_bit_depth + i]->v.push_back(STR2BITMAP(bitmaps[j]));
        }
    }
}

bool BitMapManager::exists(const std::vector<std::pair<std::string, int>>& values) {
    for (size_t i = 0; i < values.size(); i++) {
        const std::pair<std::string, int>& v = values[i];
        if (!index_bitmap_vec_[v.second]->exists(STR2BITMAP(v.first))) {
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
        index_bitmap_vec_[0]->v.push_back(STR2BITMAP(bitmaps[i]));
    }
}
