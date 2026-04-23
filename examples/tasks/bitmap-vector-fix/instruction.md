# Bitmap Vector Fix

## Background

You are given a C++ implementation of `BitMapManager` — a **multi-dimensional
hash-based string filter**. It maps string keys to integer hash values and
supports fast membership queries across multiple independent "dimensions"
(conceptually similar to a multi-column inverted index for string tags).

The code compiles without errors, but **contains bugs that cause crashes and
incorrect behavior at runtime**.

## Your Task

Fix the bugs in `bitmap_manager.cpp` so that **all tests in
`/app/bitmap_manager_test.cpp` pass** and the program exits with code 0.

## Files in `/app/`

```
/app/
├── bitmap.h                  # BitMap struct            — read-only, do NOT modify
├── hash.h                    # Hash utilities           — read-only, do NOT modify
├── bitmap_manager.h          # BitMapManager declaration — read-only, do NOT modify
├── bitmap_manager_test.cpp   # Test file               — read-only, do NOT modify
└── bitmap_manager.cpp        # ← THIS IS THE ONLY FILE YOU SHOULD FIX
```

## Compilation

```bash
g++ -std=c++11 -o /app/bitmap_manager_test \
    /app/bitmap_manager_test.cpp \
    /app/bitmap_manager.cpp
```

## Success Condition

```bash
/app/bitmap_manager_test
# Must print: FAIL: 0
# Must exit with code 0
```

## Tests Covered

The test file exercises all public methods of `BitMapManager`:

| Test | Methods exercised |
|------|-------------------|
| `test_load_bitmap` | `loadBitMap`, `exists`, `size` |
| `test_add_bitmap` | `addBitMap`, `exists`, `size` |
| `test_exists_multi_dim` | `exists` with multiple dimensions (AND semantics) |
| `test_size` | `size` after each load/add |

## Known Bugs (for reference — find them yourself)

The buggy source is in `/app/bitmap_manager.cpp`. You may inspect it freely.
There are **at least 3 distinct bugs** — all in `bitmap_manager.cpp`.

## Constraints

- **Do NOT modify** `bitmap_manager_test.cpp`, `bitmap_manager.h`,
  `bitmap.h`, or `hash.h`.
- Fix only `bitmap_manager.cpp`.
- Use only C++11 standard library. No external dependencies.
- The fix should be minimal — do not rewrite the entire architecture.
