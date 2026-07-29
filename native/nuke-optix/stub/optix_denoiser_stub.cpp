#include "hdu/optix_denoiser.h"

#include <algorithm>
#include <cstddef>

namespace hdu::optix {

int device_count() {
    return 1;
}

std::string device_name(int device_index) {
    if (device_index != 0) {
        throw Error("stub CUDA device index is out of range");
    }
    return "Stub CUDA Device";
}

void denoise(const DenoiseRequest& request) {
    if (request.beauty.pixels == nullptr || request.output.pixels == nullptr) {
        throw Error("stub denoiser requires beauty and output buffers");
    }
    if (request.beauty.width != request.output.width ||
        request.beauty.height != request.output.height) {
        throw Error("stub output dimensions must match beauty dimensions");
    }

    const std::size_t value_count =
        static_cast<std::size_t>(request.beauty.width) *
        static_cast<std::size_t>(request.beauty.height) * 4U;
    std::copy_n(request.beauty.pixels, value_count, request.output.pixels);
}

}  // namespace hdu::optix
