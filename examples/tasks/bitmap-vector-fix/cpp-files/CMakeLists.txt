cmake_minimum_required(VERSION 3.30)
project(untitled)

set(CMAKE_CXX_STANDARD 11)

add_executable(untitled main.cpp
        hash.h
        bitmap.h
        bitmap_manager.h
        bitmap_manager.cpp)

add_executable(bitmap_manager_test bitmap_manager_test.cpp
        hash.h
        bitmap.h
        bitmap_manager.h
        bitmap_manager.cpp)
