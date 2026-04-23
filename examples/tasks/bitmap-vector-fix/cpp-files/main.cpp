#include <iostream>
#include "bitmap_manager.h"

int main()
{
    BitMapManager manager = BitMapManager();
    std::cout << "Hello, World!" << std::endl;
    std::cout << manager.size() << std::endl;
    return 0;
}
