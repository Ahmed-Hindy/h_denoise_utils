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
#include <memory>
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

#define HDU_CUDA_CHECK(expression)                                              \
    do {                                                                        \
        const CUresult hdu_cuda_result = (expression);                          \
        if (hdu_cuda_result != CUDA_SUCCESS) {                                  \
            throw_cuda_error(hdu_cuda_result, #expression, __FILE__, __LINE__); \
        }                                                                       \
    } while (false)

#define HDU_OPTIX_CHECK(expression)                                             \
    do {                                                                        \
        const OptixResult hdu_optix_result = (expression);                      \
        if (hdu_optix_result != OPTIX_SUCCESS) {                                \
            throw_optix_error(                                                  \
                hdu_optix_result, #expression, __FILE__, __LINE__);             \
        }                                                                       \
    } while (false)

class PrimaryContext final {
public:
    explicit PrimaryContext(int device_index) {
        HDU_CUDA_CHECK(cuInit(0));
        HDU_CUDA_CHECK(cuDeviceGet(&device_, device_index));
        HDU_CUDA_CHECK(cuDevicePrimaryCtxRetain(&context_, device_));
    }

    ~PrimaryContext() {
        if (context_ != nullptr) {
            cuDevicePrimaryCtxRelease(device_);
        }
    }

    PrimaryContext(const PrimaryContext&) = delete;
    PrimaryContext& operator=(const PrimaryContext&) = delete;

    [[nodiscard]] CUcontext get() const { return context_; }

private:
    CUdevice device_ = 0;
    CUcontext context_ = nullptr;
};

class ScopedCurrentContext final {
public:
    explicit ScopedCurrentContext(CUcontext context) : context_(context) {
        HDU_CUDA_CHECK(cuCtxGetCurrent(&previous_context_));
        if (previous_context_ != context_) {
            HDU_CUDA_CHECK(cuCtxSetCurrent(context_));
            changed_ = true;
        }
    }

    ~ScopedCurrentContext() {
        if (changed_) {
            cuCtxSetCurrent(previous_context_);
        }
    }

    ScopedCurrentContext(const ScopedCurrentContext&) = delete;
    ScopedCurrentContext& operator=(const ScopedCurrentContext&) = delete;

private:
    CUcontext context_ = nullptr;
    CUcontext previous_context_ = nullptr;
    bool changed_ = false;
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
    Denoiser(
        OptixDeviceContext context,
        OptixDenoiserModelKind model,
        const OptixDenoiserOptions& options) {
        HDU_OPTIX_CHECK(optixDenoiserCreate(
            context,
            model,
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

class DenoiserSession::Impl final {
public:
    ~Impl() { reset_unlocked(); }

    void denoise(const DenoiseRequest& request) {
        validate_request(request);

        std::lock_guard<std::mutex> lock(mutex_);
        try {
            const int count = device_count();
            if (count == 0) {
                throw Error("no CUDA devices were found");
            }
            if (request.options.gpu_device < 0 ||
                request.options.gpu_device >= count) {
                throw Error("CUDA device index is out of range");
            }

            ensure_device(request.options.gpu_device);
            ScopedCurrentContext current(cuda_context_->get());
            ensure_denoiser(request);
            ensure_buffers(request);
            execute(request);
        } catch (...) {
            reset_unlocked();
            throw;
        }
    }

    void reset() noexcept {
        try {
            std::lock_guard<std::mutex> lock(mutex_);
            reset_unlocked();
        } catch (...) {
            // Reset is best-effort and must remain safe during error handling.
        }
    }

private:
    void ensure_device(int gpu_device) {
        if (cuda_context_ != nullptr && gpu_device_ == gpu_device) {
            return;
        }

        reset_unlocked();
        initialize_optix();
        try {
            cuda_context_ = std::make_unique<PrimaryContext>(gpu_device);
            ScopedCurrentContext current(cuda_context_->get());
            stream_ = std::make_unique<Stream>();
            optix_context_ =
                std::make_unique<DeviceContext>(cuda_context_->get());
            gpu_device_ = gpu_device;
        } catch (...) {
            reset_unlocked();
            throw;
        }
    }

    void ensure_denoiser(const DenoiseRequest& request) {
        const bool has_albedo = request.albedo.pixels != nullptr;
        const bool has_normal = request.normal.pixels != nullptr;
        const bool matches =
            denoiser_ != nullptr &&
            has_albedo_ == has_albedo &&
            has_normal_ == has_normal &&
            denoise_alpha_ == request.options.denoise_alpha &&
            hdr_ == request.options.hdr;
        if (matches) {
            return;
        }

        clear_buffers();
        denoiser_.reset();

        OptixDenoiserOptions options{};
        options.guideAlbedo = has_albedo;
        options.guideNormal = has_normal;
#if OPTIX_VERSION >= 80000
        options.denoiseAlpha = static_cast<OptixDenoiserAlphaMode>(
            request.options.denoise_alpha ? 1 : 0);
#endif
        const OptixDenoiserModelKind model = request.options.hdr
            ? OPTIX_DENOISER_MODEL_KIND_HDR
            : OPTIX_DENOISER_MODEL_KIND_LDR;
        denoiser_ =
            std::make_unique<Denoiser>(optix_context_->get(), model, options);
        has_albedo_ = has_albedo;
        has_normal_ = has_normal;
        denoise_alpha_ = request.options.denoise_alpha;
        hdr_ = request.options.hdr;
    }

    void ensure_buffers(const DenoiseRequest& request) {
        if (input_buffer_.get() != 0 &&
            width_ == request.beauty.width &&
            height_ == request.beauty.height &&
            requested_tile_width_ == request.options.tile_width &&
            requested_tile_height_ == request.options.tile_height) {
            return;
        }

        clear_buffers();
        width_ = request.beauty.width;
        height_ = request.beauty.height;
        requested_tile_width_ = request.options.tile_width;
        requested_tile_height_ = request.options.tile_height;
        image_bytes_ = image_byte_size(width_, height_);

        input_buffer_ = DeviceAllocation(image_bytes_);
        output_buffer_ = DeviceAllocation(image_bytes_);
        if (has_albedo_) {
            albedo_buffer_ = DeviceAllocation(image_bytes_);
        }
        if (has_normal_) {
            normal_buffer_ = DeviceAllocation(image_bytes_);
        }

        HDU_OPTIX_CHECK(optixDenoiserComputeMemoryResources(
            denoiser_->get(), width_, height_, &sizes_));

        use_tiling_ =
            requested_tile_width_ != 0 &&
            (requested_tile_width_ < width_ ||
             requested_tile_height_ < height_);
        tile_width_ =
            use_tiling_ ? std::min(requested_tile_width_, width_) : width_;
        tile_height_ =
            use_tiling_ ? std::min(requested_tile_height_, height_) : height_;
        overlap_ = use_tiling_ ? sizes_.overlapWindowSizeInPixels : 0U;
        scratch_size_ =
            use_tiling_ ? sizes_.withOverlapScratchSizeInBytes
                        : sizes_.withoutOverlapScratchSizeInBytes;

        state_buffer_ = DeviceAllocation(sizes_.stateSizeInBytes);
        scratch_buffer_ = DeviceAllocation(scratch_size_);
        intensity_buffer_ = DeviceAllocation(sizeof(float));

        HDU_OPTIX_CHECK(optixDenoiserSetup(
            denoiser_->get(),
            stream_->get(),
            tile_width_ + 2U * overlap_,
            tile_height_ + 2U * overlap_,
            state_buffer_.get(),
            sizes_.stateSizeInBytes,
            scratch_buffer_.get(),
            scratch_size_));
    }

    void execute(const DenoiseRequest& request) {
        HDU_CUDA_CHECK(cuMemcpyHtoDAsync(
            input_buffer_.get(),
            request.beauty.pixels,
            image_bytes_,
            stream_->get()));

        OptixDenoiserLayer layer{};
        layer.input = make_image(input_buffer_, width_, height_);
        layer.output = make_image(output_buffer_, width_, height_);

        OptixDenoiserGuideLayer guide{};
        if (has_albedo_) {
            HDU_CUDA_CHECK(cuMemcpyHtoDAsync(
                albedo_buffer_.get(),
                request.albedo.pixels,
                image_bytes_,
                stream_->get()));
            guide.albedo = make_image(albedo_buffer_, width_, height_);
        }
        if (has_normal_) {
            HDU_CUDA_CHECK(cuMemcpyHtoDAsync(
                normal_buffer_.get(),
                request.normal.pixels,
                image_bytes_,
                stream_->get()));
            guide.normal = make_image(normal_buffer_, width_, height_);
        }

        HDU_OPTIX_CHECK(optixDenoiserComputeIntensity(
            denoiser_->get(),
            stream_->get(),
            &layer.input,
            intensity_buffer_.get(),
            scratch_buffer_.get(),
            scratch_size_));

        OptixDenoiserParams parameters{};
        parameters.hdrIntensity = intensity_buffer_.get();
        parameters.blendFactor = request.options.blend_factor;
#if OPTIX_VERSION < 80000
        parameters.denoiseAlpha = static_cast<OptixDenoiserAlphaMode>(
            request.options.denoise_alpha ? 1 : 0);
#endif

        if (use_tiling_) {
            HDU_OPTIX_CHECK(optixUtilDenoiserInvokeTiled(
                denoiser_->get(),
                stream_->get(),
                &parameters,
                state_buffer_.get(),
                sizes_.stateSizeInBytes,
                &guide,
                &layer,
                1U,
                scratch_buffer_.get(),
                scratch_size_,
                overlap_,
                tile_width_,
                tile_height_));
        } else {
            HDU_OPTIX_CHECK(optixDenoiserInvoke(
                denoiser_->get(),
                stream_->get(),
                &parameters,
                state_buffer_.get(),
                sizes_.stateSizeInBytes,
                &guide,
                &layer,
                1U,
                0U,
                0U,
                scratch_buffer_.get(),
                scratch_size_));
        }

        HDU_CUDA_CHECK(cuMemcpyDtoHAsync(
            request.output.pixels,
            output_buffer_.get(),
            image_bytes_,
            stream_->get()));
        HDU_CUDA_CHECK(cuStreamSynchronize(stream_->get()));

        if (!request.options.denoise_alpha) {
            const std::size_t pixel_count =
                static_cast<std::size_t>(width_) *
                static_cast<std::size_t>(height_);
            for (std::size_t pixel = 0; pixel < pixel_count; ++pixel) {
                request.output.pixels[pixel * 4U + 3U] =
                    request.beauty.pixels[pixel * 4U + 3U];
            }
        }
    }

    void clear_buffers() noexcept {
        intensity_buffer_ = {};
        scratch_buffer_ = {};
        state_buffer_ = {};
        normal_buffer_ = {};
        albedo_buffer_ = {};
        output_buffer_ = {};
        input_buffer_ = {};
        sizes_ = {};
        width_ = 0;
        height_ = 0;
        requested_tile_width_ = 0;
        requested_tile_height_ = 0;
        tile_width_ = 0;
        tile_height_ = 0;
        overlap_ = 0;
        image_bytes_ = 0;
        scratch_size_ = 0;
        use_tiling_ = false;
    }

    void reset_unlocked() noexcept {
        if (cuda_context_ != nullptr) {
            try {
                ScopedCurrentContext current(cuda_context_->get());
                if (stream_ != nullptr) {
                    cuStreamSynchronize(stream_->get());
                }
                clear_buffers();
                denoiser_.reset();
                stream_.reset();
                optix_context_.reset();
            } catch (...) {
                // The context may already be invalid; release host-side handles.
                clear_buffers();
                denoiser_.reset();
                stream_.reset();
                optix_context_.reset();
            }
        } else {
            clear_buffers();
            denoiser_.reset();
            stream_.reset();
            optix_context_.reset();
        }
        cuda_context_.reset();
        gpu_device_ = -1;
        has_albedo_ = false;
        has_normal_ = false;
        denoise_alpha_ = false;
        hdr_ = true;
    }

    std::mutex mutex_;
    int gpu_device_ = -1;
    std::unique_ptr<PrimaryContext> cuda_context_;
    std::unique_ptr<Stream> stream_;
    std::unique_ptr<DeviceContext> optix_context_;
    std::unique_ptr<Denoiser> denoiser_;

    bool has_albedo_ = false;
    bool has_normal_ = false;
    bool denoise_alpha_ = false;
    bool hdr_ = true;

    unsigned int width_ = 0;
    unsigned int height_ = 0;
    unsigned int requested_tile_width_ = 0;
    unsigned int requested_tile_height_ = 0;
    unsigned int tile_width_ = 0;
    unsigned int tile_height_ = 0;
    unsigned int overlap_ = 0;
    bool use_tiling_ = false;
    std::size_t image_bytes_ = 0;
    std::size_t scratch_size_ = 0;
    OptixDenoiserSizes sizes_{};

    DeviceAllocation input_buffer_;
    DeviceAllocation output_buffer_;
    DeviceAllocation albedo_buffer_;
    DeviceAllocation normal_buffer_;
    DeviceAllocation state_buffer_;
    DeviceAllocation scratch_buffer_;
    DeviceAllocation intensity_buffer_;
};

DenoiserSession::DenoiserSession() : impl_(std::make_unique<Impl>()) {}

DenoiserSession::~DenoiserSession() = default;

DenoiserSession::DenoiserSession(DenoiserSession&&) noexcept = default;

DenoiserSession& DenoiserSession::operator=(DenoiserSession&&) noexcept = default;

void DenoiserSession::denoise(const DenoiseRequest& request) {
    if (impl_ == nullptr) {
        impl_ = std::make_unique<Impl>();
    }
    impl_->denoise(request);
}

void DenoiserSession::reset() noexcept {
    if (impl_ != nullptr) {
        impl_->reset();
    }
}

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
    DenoiserSession session;
    session.denoise(request);
}

}  // namespace hdu::optix
