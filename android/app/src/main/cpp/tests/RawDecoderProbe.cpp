#include "RawDecoder.h"

#include <iostream>

int main(int argc, char** argv) {
    std::cout << "LibRaw " << spektra::rawVersion() << '\n';
    const bool supported = spektra::rawCameraSupported("Sony ILCE-7CR (A7CR)");
    std::cout << "Sony ILCE-7CR (A7CR): " << (supported ? "supported" : "missing") << '\n';
    if (!supported) return 2;
    if (argc < 2) return 0;
    std::atomic<bool> cancelled{false};
    try {
        auto info = spektra::inspectRaw(argv[1], cancelled);
        std::cout << "oriented full size: " << info.width << 'x' << info.height
                  << "; sensor: " << info.rawWidth << 'x' << info.rawHeight
                  << "; flip: " << info.flip << '\n';
        if (argc > 2) {
            info = spektra::developRaw(argv[1], argv[2], false, cancelled);
            std::cout << "RGB16LE: " << info.width << 'x' << info.height << '\n';
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
