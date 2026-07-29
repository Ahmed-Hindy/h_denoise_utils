#include "hdu/optix_denoiser.h"

#include <DDImage/ChannelSet.h>
#include <DDImage/Iop.h>
#include <DDImage/Knobs.h>
#include <DDImage/PlanarIop.h>
#include <DDImage/RequestOutput.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <exception>
#include <functional>
#include <string>
#include <utility>
#include <vector>

#ifndef HDU_VERSION
#define HDU_VERSION "dev"
#endif

namespace {

using DD::Image::Box;
using DD::Image::Chan_Alpha;
using DD::Image::Chan_Black;
using DD::Image::Chan_Blue;
using DD::Image::Chan_Green;
using DD::Image::Chan_Red;
using DD::Image::Channel;
using DD::Image::ChannelSet;
using DD::Image::Enumeration_knob;
using DD::Image::Float_knob;
using DD::Image::ImagePlane;
using DD::Image::Int_knob;
using DD::Image::Iop;
using DD::Image::IRange;
using DD::Image::Knob_Callback;
using DD::Image::Mask_RGB;
using DD::Image::Mask_RGBA;
using DD::Image::Op;
using DD::Image::PlanarIop;
using DD::Image::RequestOutput;
using DD::Image::SetRange;
using DD::Image::Text_knob;
using DD::Image::Tooltip;
using DD::Image::Bool_knob;

constexpr const char* kClass = "HOptixDenoise";
constexpr const char* kHelp =
    "Denoises noisy CG beauty renders in-process with NVIDIA OptiX. "
    "Optional albedo and normal guide inputs improve detail preservation. "
    "The normal input requires albedo.";

[[nodiscard]] ChannelSet available_channels(Iop& input, const ChannelSet& requested) {
    ChannelSet result = requested;
    result &= input.info().channels();
    return result;
}

[[nodiscard]] float read_channel(
    const ImagePlane& plane,
    int x,
    int y,
    Channel channel,
    float fallback) {
    const int channel_index = plane.chanNo(channel);
    return channel_index >= 0 ? plane.at(x, y, channel_index) : fallback;
}

[[nodiscard]] bool fill_rgba_buffer(
    const ImagePlane& plane,
    const Box& bounds,
    std::vector<float>& destination,
    bool remap_unsigned_normals,
    const std::function<bool()>& abort_requested) {
    const std::size_t pixel_count =
        static_cast<std::size_t>(bounds.w()) * static_cast<std::size_t>(bounds.h());
    destination.assign(pixel_count * 4U, 0.0F);

    for (int y = bounds.y(); y < bounds.t(); ++y) {
        if (abort_requested()) {
            return false;
        }
        for (int x = bounds.x(); x < bounds.r(); ++x) {
            const std::size_t pixel =
                static_cast<std::size_t>(y - bounds.y()) *
                    static_cast<std::size_t>(bounds.w()) +
                static_cast<std::size_t>(x - bounds.x());
            float red = read_channel(plane, x, y, Chan_Red, 0.0F);
            float green = read_channel(plane, x, y, Chan_Green, 0.0F);
            float blue = read_channel(plane, x, y, Chan_Blue, 0.0F);
            if (remap_unsigned_normals) {
                red = red * 2.0F - 1.0F;
                green = green * 2.0F - 1.0F;
                blue = blue * 2.0F - 1.0F;
            }

            destination[pixel * 4U + 0U] = red;
            destination[pixel * 4U + 1U] = green;
            destination[pixel * 4U + 2U] = blue;
            destination[pixel * 4U + 3U] =
                read_channel(plane, x, y, Chan_Alpha, 1.0F);
        }
    }
    return true;
}

class HOptixDenoise final : public PlanarIop {
public:
    explicit HOptixDenoise(Node* node) : PlanarIop(node) {}

    [[nodiscard]] int minimum_inputs() const override { return 1; }
    [[nodiscard]] int maximum_inputs() const override { return 3; }

    [[nodiscard]] const char* input_label(int input_index, char*) const override {
        switch (input_index) {
            case 0:
                return "beauty";
            case 1:
                return "albedo";
            case 2:
                return "normal";
            default:
                return nullptr;
        }
    }

    [[nodiscard]] const char* Class() const override { return kClass; }
    [[nodiscard]] const char* node_help() const override { return kHelp; }
    [[nodiscard]] bool renderFullPlanes() const override { return true; }
    [[nodiscard]] PackedPreference packedPreference() const override {
        return ePackedPreferencePacked;
    }

    void knobs(Knob_Callback callback) override {
        Float_knob(callback, &blend_factor_, IRange(0.0, 1.0), "blend", "input blend");
        Tooltip(
            callback,
            "Mix the noisy input back into the denoised result. 0 is fully denoised; "
            "1 is the original input.");

        static const char* tile_sizes[] = {
            "Full frame", "512 x 512", "1024 x 1024", "2048 x 2048", nullptr};
        Enumeration_knob(
            callback, &tile_preset_, tile_sizes, "tile_size", "tile size");
        Tooltip(
            callback,
            "OptiX processing tile size. Smaller tiles reduce peak VRAM use but can be slower.");

        Int_knob(callback, &gpu_device_, IRange(0, 15), "gpu_device", "GPU device");
        Tooltip(callback, "Zero-based CUDA device index.");

        static const char* normal_encodings[] = {
            "Signed (-1 to 1)", "Unsigned (0 to 1)", nullptr};
        Enumeration_knob(
            callback,
            &normal_encoding_,
            normal_encodings,
            "normal_encoding",
            "normal encoding");
        Tooltip(
            callback,
            "Select Unsigned only when the normal pass is stored in the 0-to-1 range. "
            "It will be remapped to -1-to-1 before denoising.");

        Bool_knob(
            callback,
            &passthrough_on_error_,
            "passthrough_on_error",
            "passthrough on error");
        Tooltip(
            callback,
            "Return the beauty input unchanged if CUDA or OptiX fails instead of failing the render.");

        Text_knob(
            callback,
            (std::string("h_denoise_utils ") + HDU_VERSION +
             " | NVIDIA OptiX spatial denoiser")
                .c_str());
    }

    void _validate(bool for_real) override {
        copy_info();
        set_out_channels(input0().info().channels());

        if (input(2) != nullptr && input(1) == nullptr) {
            error("HOptixDenoise: the normal guide requires an albedo guide");
        }

        const auto& beauty_info = input0().info();
        for (int input_index = 1; input_index <= 2; ++input_index) {
            Iop* guide = input(input_index);
            if (guide == nullptr) {
                continue;
            }

            guide->validate(for_real);
            const auto& guide_info = guide->info();
            const bool matching_geometry =
                guide_info.format().width() == beauty_info.format().width() &&
                guide_info.format().height() == beauty_info.format().height() &&
                guide_info.x() == beauty_info.x() &&
                guide_info.y() == beauty_info.y() &&
                guide_info.r() == beauty_info.r() &&
                guide_info.t() == beauty_info.t();
            if (!matching_geometry) {
                error(
                    "HOptixDenoise: %s must match the beauty format and data window",
                    input_index == 1 ? "albedo" : "normal");
            }

            const ChannelSet guide_channels = guide_info.channels();
            if (!guide_channels.contains(Chan_Red) ||
                !guide_channels.contains(Chan_Green) ||
                !guide_channels.contains(Chan_Blue)) {
                error(
                    "HOptixDenoise: %s must provide red, green, and blue channels",
                    input_index == 1 ? "albedo" : "normal");
            }
        }
    }

    void getRequests(
        const Box& box,
        const ChannelSet& channels,
        int count,
        RequestOutput& requests) const override {
        ChannelSet beauty_channels = channels;
        beauty_channels += Mask_RGBA;
        beauty_channels &= input0().info().channels();
        requests.request(&input0(), box, beauty_channels, count);

        if (input(1) != nullptr) {
            ChannelSet guide_channels = Mask_RGB;
            guide_channels &= input(1)->info().channels();
            requests.request(input(1), box, guide_channels, count);
        }
        if (input(2) != nullptr) {
            ChannelSet guide_channels = Mask_RGB;
            guide_channels &= input(2)->info().channels();
            requests.request(input(2), box, guide_channels, count);
        }
    }

    void renderStripe(ImagePlane& output_plane) override {
        const Box bounds = output_plane.bounds();
        const ChannelSet output_channels = output_plane.channels();

        ChannelSet rgb_intersection = output_channels;
        rgb_intersection &= Mask_RGB;
        if (rgb_intersection.empty()) {
            passthrough(output_plane);
            return;
        }

        try {
            if (aborted()) {
                passthrough(output_plane);
                return;
            }

            const std::function<bool()> abort_requested =
                [this] { return aborted(); };

            ChannelSet beauty_channels = available_channels(input0(), Mask_RGBA);
            ImagePlane beauty_plane(bounds, true, beauty_channels);
            input0().fetchPlane(beauty_plane);

            std::vector<float> beauty_pixels;
            std::vector<float> output_pixels;
            if (!fill_rgba_buffer(
                    beauty_plane,
                    bounds,
                    beauty_pixels,
                    false,
                    abort_requested)) {
                passthrough(output_plane);
                return;
            }
            output_pixels.resize(beauty_pixels.size());

            std::vector<float> albedo_pixels;
            std::vector<float> normal_pixels;
            hdu::optix::ImageView albedo_view{};
            hdu::optix::ImageView normal_view{};

            if (input(1) != nullptr) {
                ChannelSet channels = available_channels(*input(1), Mask_RGB);
                ImagePlane albedo_plane(bounds, true, channels);
                input(1)->fetchPlane(albedo_plane);
                if (!fill_rgba_buffer(
                        albedo_plane,
                        bounds,
                        albedo_pixels,
                        false,
                        abort_requested)) {
                    passthrough(output_plane);
                    return;
                }
                albedo_view = {
                    albedo_pixels.data(),
                    static_cast<unsigned int>(bounds.w()),
                    static_cast<unsigned int>(bounds.h())};
            }

            if (input(2) != nullptr) {
                ChannelSet channels = available_channels(*input(2), Mask_RGB);
                ImagePlane normal_plane(bounds, true, channels);
                input(2)->fetchPlane(normal_plane);
                if (!fill_rgba_buffer(
                        normal_plane,
                        bounds,
                        normal_pixels,
                        normal_encoding_ == 1,
                        abort_requested)) {
                    passthrough(output_plane);
                    return;
                }
                normal_view = {
                    normal_pixels.data(),
                    static_cast<unsigned int>(bounds.w()),
                    static_cast<unsigned int>(bounds.h())};
            }

            const auto [tile_width, tile_height] = tile_dimensions();
            hdu::optix::DenoiseRequest request{};
            request.beauty = {
                beauty_pixels.data(),
                static_cast<unsigned int>(bounds.w()),
                static_cast<unsigned int>(bounds.h())};
            request.albedo = albedo_view;
            request.normal = normal_view;
            request.output = {
                output_pixels.data(),
                static_cast<unsigned int>(bounds.w()),
                static_cast<unsigned int>(bounds.h())};
            request.options.gpu_device = gpu_device_;
            request.options.blend_factor =
                std::clamp(blend_factor_, 0.0F, 1.0F);
            request.options.tile_width = tile_width;
            request.options.tile_height = tile_height;
            request.options.denoise_alpha = false;

            denoiser_session_.denoise(request);

            if (aborted()) {
                passthrough(output_plane);
                return;
            }
            if (!write_output(
                    output_plane,
                    beauty_plane,
                    output_pixels,
                    abort_requested)) {
                passthrough(output_plane);
            }
        } catch (const std::exception& exception) {
            denoiser_session_.reset();
            if (passthrough_on_error_) {
                warning("HOptixDenoise: %s", exception.what());
                passthrough(output_plane);
                return;
            }
            error("HOptixDenoise: %s", exception.what());
            output_plane.makeWritable();
            for (Channel channel = output_plane.channels().first();
                 channel != Chan_Black;
                 channel = output_plane.channels().next(channel)) {
                output_plane.fillChannelThreaded(channel, 0.0F);
            }
        }
    }

private:
    [[nodiscard]] std::pair<unsigned int, unsigned int> tile_dimensions() const {
        switch (tile_preset_) {
            case 1:
                return {512U, 512U};
            case 2:
                return {1024U, 1024U};
            case 3:
                return {2048U, 2048U};
            default:
                return {0U, 0U};
        }
    }

    void passthrough(ImagePlane& output_plane) {
        ChannelSet channels = available_channels(input0(), output_plane.channels());
        ImagePlane source(output_plane.bounds(), output_plane.packed(), channels);
        input0().fetchPlane(source);
        output_plane.copyIntersectionFrom(source, true);
    }

    [[nodiscard]] static bool write_output(
        ImagePlane& output_plane,
        const ImagePlane& beauty_plane,
        const std::vector<float>& denoised_pixels,
        const std::function<bool()>& abort_requested) {
        output_plane.makeWritable();
        const Box bounds = output_plane.bounds();

        for (Channel channel = output_plane.channels().first();
             channel != Chan_Black;
             channel = output_plane.channels().next(channel)) {
            const int output_channel = output_plane.chanNo(channel);
            const int source_channel = beauty_plane.chanNo(channel);
            for (int y = bounds.y(); y < bounds.t(); ++y) {
                if (abort_requested()) {
                    return false;
                }
                for (int x = bounds.x(); x < bounds.r(); ++x) {
                    const std::size_t pixel =
                        static_cast<std::size_t>(y - bounds.y()) *
                            static_cast<std::size_t>(bounds.w()) +
                        static_cast<std::size_t>(x - bounds.x());
                    float value = source_channel >= 0
                                      ? beauty_plane.at(x, y, source_channel)
                                      : 0.0F;
                    if (channel == Chan_Red) {
                        value = denoised_pixels[pixel * 4U + 0U];
                    } else if (channel == Chan_Green) {
                        value = denoised_pixels[pixel * 4U + 1U];
                    } else if (channel == Chan_Blue) {
                        value = denoised_pixels[pixel * 4U + 2U];
                    }
                    output_plane.writableAt(x, y, output_channel) = value;
                }
            }
        }
        return true;
    }

    hdu::optix::DenoiserSession denoiser_session_;
    float blend_factor_ = 0.0F;
    int tile_preset_ = 2;
    int gpu_device_ = 0;
    int normal_encoding_ = 0;
    bool passthrough_on_error_ = true;
};

Op* build(Node* node) {
    return new HOptixDenoise(node);
}

const Iop::Description description(kClass, build);

}  // namespace
