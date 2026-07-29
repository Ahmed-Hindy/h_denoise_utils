#pragma once

#include <cstddef>
#include <stdexcept>
#include <string>

namespace hdu::optix {

struct ImageView {
    const float* pixels = nullptr;
    unsigned int width = 0;
    unsigned int height = 0;
};

struct MutableImageView {
    float* pixels = nullptr;
    unsigned int width = 0;
    unsigned int height = 0;
};

struct DenoiseOptions {
    int gpu_device = 0;
    float blend_factor = 0.0F;
    unsigned int tile_width = 0;
    unsigned int tile_height = 0;
    bool denoise_alpha = false;
    bool hdr = true;
};

struct DenoiseRequest {
    ImageView beauty;
    ImageView albedo;
    ImageView normal;
    MutableImageView output;
    DenoiseOptions options;
};

class Error final : public std::runtime_error {
public:
    explicit Error(const std::string& message) : std::runtime_error(message) {}
};

[[nodiscard]] int device_count();
[[nodiscard]] std::string device_name(int device_index);
void denoise(const DenoiseRequest& request);

}  // namespace hdu::optix
