#define NOMINMAX

#include "hdu/optix_denoiser.h"

#include <optix.h>
#include <optix_denoiser_tiling.h>
#include <optix_function_table_definition.h>
#include <optix_stubs.h>

#include <cuda.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <mutex>
#include <sstream>
#include <utility>

namespace hdu::optix {
namespace {

[[noreturn]] void throw_cuda_error(
    CUresult result,
    const char* expression,
    const char* file,
    int line) {
    const char* error_name = nullptr;
    const char* error_text = nullptr;
    cuGetErrorName(result, &error_name);
    cuGetErrorString(result, &error_text);

    std::ostringstream message;
    message << "CUDA driver call failed at " << file << ':' << line << ": "
            << expression << " returned "
            << (error_name != nullptr ? error_name : "unknown error");
    if (error_text != nullptr) {
        message << " (" << error_text << ')';
    }
    throw Error(message.str());
}

[[noreturn]] void throw_optix_error(
    OptixResult result,
    const char* expression,
    const char* file,
    int line) {
    std::ostringstream message;
    message << "OptiX call failed at " << file << ':' << line << ": "
            << expression << " returned " << optixGetErrorName(result);
    throw Error(message.str());
}

#define HDU_CUDA_CHECK(expression)                                             \
    do {                                                                       \
        const CUresult hdu_cuda_result = (expression);                         \
        if (hdu_cuda_result != CUDA_SUCCESS) {                                 \
            throw_cuda_error(hdu_cuda_result, #expression, __FILE__, __LINE__); \
        }                                                                      \
    } while (false)

#define HDU_OPTIX_CHECK(expression)                                            \
    do {                                                                       \
        const OptixResult hdu_optix_result = (expression);                     \
        if (hdu_optix_result != OPTIX_SUCCESS) {                               \
            throw_optix_error(hdu_optix_result, #expression, __FILE__, __LINE__); \
        }                                                                      \
    } while (false)

class PrimaryContext final {
public:
    explicit PrimaryContext(int device_index) {
        HDU_CUDA_CHECK(cuInit(0));
        HDU_CUDA_CHECK(cuDeviceGet(&device_, device_index));
        HDU_CUDA_CHECK(cuCtxGetCurrent(&previous_context_));
        HDU_CUDA_CHECK(cuDevicePrimaryCtxRetain(&context_, device_));
        try {
            HDU_CUDA_CHECK(cuCtxSetCurrent(context_));
        } catch (...) {
            cuDevicePrimaryCtxRelease(device_);
            context_ = nullptr;
            throw;
        }
    }

    ~PrimaryContext() {
        if (context_ != nullptr) {
            cuCtxSetCurrent(previous_context_);
            cuDevicePrimaryCtxRelease(device_);
        }
    }

    PrimaryContext(const PrimaryContext&) = delete;
    PrimaryContext& operator=(const PrimaryContext&) = delete;

    [[nodiscard]] CUcontext get() const { return context_; }

private:
    CUdevice device_ = 0;
    CUcontext context_ = nullptr;
    CUcontext previous_context_ = nullptr;
};

class DeviceAllocation final {
public:
    DeviceAllocation() = default;

    explicit DeviceAllocation(std::size_t size) {
        if (size > 0) {
            HDU_CUDA_CHECK(cuMemAlloc(&pointer_, size));
        }
    }

    ~DeviceAllocation() {
        if (pointer_ != 0) {
            cuMemFree(pointer_);
        }
    }

    DeviceAllocation(const DeviceAllocation&) = delete;
    DeviceAllocation& operator=(const DeviceAllocation&) = delete;

    DeviceAllocation(DeviceAllocation&& other) noexcept
        : pointer_(std::exchange(other.pointer_, 0)) {}

    DeviceAllocation& operator=(DeviceAllocation&& other) noexcept {
        if (this != &other) {
            if (pointer_ != 0) {
                cuMemFree(pointer_);
            }
            pointer_ = std::exchange(other.pointer_, 0);
        }
        return *this;
    }

    [[nodiscard]] CUdeviceptr get() const { return pointer_; }

private:
    CUdeviceptr pointer_ = 0;
};

class Stream final {
public:
    Stream() { HDU_CUDA_CHECK(cuStreamCreate(&stream_, CU_STREAM_DEFAULT)); }

    ~Stream() {
        if (stream_ != nullptr) {
            cuStreamDestroy(stream_);
        }
    }

    Stream(const Stream&) = delete;
    Stream& operator=(const Stream&) = delete;

    [[nodiscard]] CUstream get() const { return stream_; }

private:
    CUstream stream_ = nullptr;
};

class DeviceContext final {
public:
    explicit DeviceContext(CUcontext cuda_context) {
        HDU_OPTIX_CHECK(
            optixDeviceContextCreate(cuda_context, nullptr, &context_));
    }

    ~DeviceContext() {
        if (context_ != nullptr) {
            optixDeviceContextDestroy(context_);
        }
    }

    DeviceContext(const DeviceContext&) = delete;
    DeviceContext& operator=(const DeviceContext&) = delete;

    [[nodiscard]] OptixDeviceContext get() const { return context_; }

private:
    OptixDeviceContext context_ = nullptr;
};

class Denoiser final {
public:
    Denoiser(OptixDeviceContext context, const OptixDenoiserOptions& options) {
        HDU_OPTIX_CHECK(optixDenoiserCreate(
            context,
            OPTIX_DENOISER_MODEL_KIND_HDR,
            &options,
            &denoiser_));
    }

    ~Denoiser() {
        if (denoiser_ != nullptr) {
            optixDenoiserDestroy(denoiser_);
        }
    }

    Denoiser(const Denoiser&) = delete;
    Denoiser& operator=(const Denoiser&) = delete;

    [[nodiscard]] OptixDenoiser get() const { return denoiser_; }

private:
    OptixDenoiser denoiser_ = nullptr;
};

[[nodiscard]] std::size_t image_byte_size(
    unsigned int width,
    unsigned int height) {
    return static_cast<std::size_t>(width) *
           static_cast<std::size_t>(height) * 4U * sizeof(float);
}

void validate_image(const ImageView& image, const char* name, bool required) {
    const bool supplied = image.pixels != nullptr;
    if (required && !supplied) {
        throw Error(std::string(name) + " pixels are required");
    }
    if (!supplied) {
        if (image.width != 0 || image.height != 0) {
            throw Error(std::string(name) +
                        " dimensions were supplied without pixels");
        }
        return;
    }
    if (image.width == 0 || image.height == 0) {
        throw Error(std::string(name) + " dimensions must be non-zero");
    }
}

void validate_request(const DenoiseRequest& request) {
    validate_image(request.beauty, "beauty", true);
    validate_image(request.albedo, "albedo", false);
    validate_image(request.normal, "normal", false);

    if (request.output.pixels == nullptr) {
        throw Error("output pixels are required");
    }
    if (request.output.width != request.beauty.width ||
        request.output.height != request.beauty.height) {
        throw Error("output dimensions must match beauty dimensions");
    }
    if (request.normal.pixels != nullptr && request.albedo.pixels == nullptr) {
        throw Error("normal guide requires an albedo guide");
    }

    for (const ImageView* guide : {&request.albedo, &request.normal}) {
        if (guide->pixels != nullptr &&
            (guide->width != request.beauty.width ||
             guide->height != request.beauty.height)) {
            throw Error("guide dimensions must match beauty dimensions");
        }
    }

    if (!std::isfinite(request.options.blend_factor) ||
        request.options.blend_factor < 0.0F ||
        request.options.blend_factor > 1.0F) {
        throw Error("blend factor must be between 0 and 1");
    }
    if ((request.options.tile_width == 0) !=
        (request.options.tile_height == 0)) {
        throw Error(
            "tile width and height must both be zero or both be non-zero");
    }
}

[[nodiscard]] OptixImage2D make_image(
    const DeviceAllocation& allocation,
    unsigned int width,
    unsigned int height) {
    OptixImage2D image{};
    image.data = allocation.get();
    image.width = width;
    image.height = height;
    image.rowStrideInBytes =
        static_cast<unsigned int>(width * 4U * sizeof(float));
    image.pixelStrideInBytes = 4U * sizeof(float);
    image.format = OPTIX_PIXEL_FORMAT_FLOAT4;
    return image;
}

void initialize_optix() {
    static std::once_flag flag;
    static OptixResult result = OPTIX_SUCCESS;
    std::call_once(flag, [] { result = optixInit(); });
    if (result != OPTIX_SUCCESS) {
        throw_optix_error(result, "optixInit()", __FILE__, __LINE__);
    }
}

void initialize_cuda() {
    HDU_CUDA_CHECK(cuInit(0));
}

}  // namespace

int device_count() {
    initialize_cuda();
    int count = 0;
    HDU_CUDA_CHECK(cuDeviceGetCount(&count));
    return count;
}

std::string device_name(int device_index) {
    const int count = device_count();
    if (device_index < 0 || device_index >= count) {
        throw Error("CUDA device index is out of range");
    }

    CUdevice device = 0;
    HDU_CUDA_CHECK(cuDeviceGet(&device, device_index));
    char name[256]{};
    HDU_CUDA_CHECK(cuDeviceGetName(name, sizeof(name), device));
    return name;
}

void denoise(const DenoiseRequest& request) {
    validate_request(request);

    const int count = device_count();
    if (count == 0) {
        throw Error("no CUDA devices were found");
    }
    if (request.options.gpu_device < 0 ||
        request.options.gpu_device >= count) {
        throw Error("CUDA device index is out of range");
    }

    PrimaryContext cuda_context(request.options.gpu_device);
    initialize_optix();
    Stream stream;
    DeviceContext optix_context(cuda_context.get());

    OptixDenoiserOptions denoiser_options{};
    denoiser_options.guideAlbedo = request.albedo.pixels != nullptr;
    denoiser_options.guideNormal = request.normal.pixels != nullptr;
#if OPTIX_VERSION >= 80000
    denoiser_options.denoiseAlpha = static_cast<OptixDenoiserAlphaMode>(
        request.options.denoise_alpha ? 1 : 0);
#endif

    Denoiser denoiser(optix_context.get(), denoiser_options);

    const unsigned int width = request.beauty.width;
    const unsigned int height = request.beauty.height;
    const std::size_t bytes = image_byte_size(width, height);

    DeviceAllocation input_buffer(bytes);
    DeviceAllocation output_buffer(bytes);
    HDU_CUDA_CHECK(cuMemcpyHtoDAsync(
        input_buffer.get(), request.beauty.pixels, bytes, stream.get()));

    OptixDenoiserLayer layer{};
    layer.input = make_image(input_buffer, width, height);
    layer.output = make_image(output_buffer, width, height);

    DeviceAllocation albedo_buffer;
    DeviceAllocation normal_buffer;
    OptixDenoiserGuideLayer guide{};

    if (request.albedo.pixels != nullptr) {
        albedo_buffer = DeviceAllocation(bytes);
        HDU_CUDA_CHECK(cuMemcpyHtoDAsync(
            albedo_buffer.get(), request.albedo.pixels, bytes, stream.get()));
        guide.albedo = make_image(albedo_buffer, width, height);
    }
    if (request.normal.pixels != nullptr) {
        normal_buffer = DeviceAllocation(bytes);
        HDU_CUDA_CHECK(cuMemcpyHtoDAsync(
            normal_buffer.get(), request.normal.pixels, bytes, stream.get()));
        guide.normal = make_image(normal_buffer, width, height);
    }

    OptixDenoiserSizes sizes{};
    HDU_OPTIX_CHECK(optixDenoiserComputeMemoryResources(
        denoiser.get(), width, height, &sizes));

    const bool use_tiling =
        request.options.tile_width != 0 &&
        (request.options.tile_width < width ||
         request.options.tile_height < height);
    const unsigned int tile_width =
        use_tiling ? std::min(request.options.tile_width, width) : width;
    const unsigned int tile_height =
        use_tiling ? std::min(request.options.tile_height, height) : height;
    const unsigned int overlap =
        use_tiling ? sizes.overlapWindowSizeInPixels : 0U;
    const std::size_t scratch_size =
        use_tiling ? sizes.withOverlapScratchSizeInBytes
                   : sizes.withoutOverlapScratchSizeInBytes;

    DeviceAllocation state_buffer(sizes.stateSizeInBytes);
    DeviceAllocation scratch_buffer(scratch_size);
    DeviceAllocation intensity_buffer(sizeof(float));

    HDU_OPTIX_CHECK(optixDenoiserSetup(
        denoiser.get(),
        stream.get(),
        tile_width + 2U * overlap,
        tile_height + 2U * overlap,
        state_buffer.get(),
        sizes.stateSizeInBytes,
        scratch_buffer.get(),
        scratch_size));

    HDU_OPTIX_CHECK(optixDenoiserComputeIntensity(
        denoiser.get(),
        stream.get(),
        &layer.input,
        intensity_buffer.get(),
        scratch_buffer.get(),
        scratch_size));

    OptixDenoiserParams parameters{};
    parameters.hdrIntensity = intensity_buffer.get();
    parameters.blendFactor = request.options.blend_factor;
#if OPTIX_VERSION < 80000
    parameters.denoiseAlpha = static_cast<OptixDenoiserAlphaMode>(
        request.options.denoise_alpha ? 1 : 0);
#endif

    if (use_tiling) {
        HDU_OPTIX_CHECK(optixUtilDenoiserInvokeTiled(
            denoiser.get(),
            stream.get(),
            &parameters,
            state_buffer.get(),
            sizes.stateSizeInBytes,
            &guide,
            &layer,
            1U,
            scratch_buffer.get(),
            scratch_size,
            overlap,
            tile_width,
            tile_height));
    } else {
        HDU_OPTIX_CHECK(optixDenoiserInvoke(
            denoiser.get(),
            stream.get(),
            &parameters,
            state_buffer.get(),
            sizes.stateSizeInBytes,
            &guide,
            &layer,
            1U,
            0U,
            0U,
            scratch_buffer.get(),
            scratch_size));
    }

    HDU_CUDA_CHECK(cuMemcpyDtoHAsync(
        request.output.pixels, output_buffer.get(), bytes, stream.get()));
    HDU_CUDA_CHECK(cuStreamSynchronize(stream.get()));

    if (!request.options.denoise_alpha) {
        const std::size_t pixel_count =
            static_cast<std::size_t>(width) *
            static_cast<std::size_t>(height);
        for (std::size_t pixel = 0; pixel < pixel_count; ++pixel) {
            request.output.pixels[pixel * 4U + 3U] =
                request.beauty.pixels[pixel * 4U + 3U];
        }
    }
}

}  // namespace hdu::optix
