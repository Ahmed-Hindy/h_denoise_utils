#include "oidn_bridge_protocol.h"

#include <DDImage/ChannelSet.h>
#include <DDImage/Iop.h>
#include <DDImage/Knobs.h>
#include <DDImage/PlanarIop.h>
#include <DDImage/RequestOutput.h>

#ifdef _WIN32
#include <Windows.h>
#endif

#include <algorithm>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <functional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

#ifndef HDU_VERSION
#define HDU_VERSION "dev"
#endif

namespace {

using DD::Image::Bool_knob;
using DD::Image::Box;
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
using DD::Image::Text_knob;
using DD::Image::Tooltip;

constexpr const char* kClass = "HOidnDenoise";
constexpr const char* kHelp =
    "Denoises noisy CG beauty renders with Intel Open Image Denoise on CUDA. "
    "OIDN runs in an isolated helper process to avoid runtime conflicts with Nuke. "
    "Optional albedo and normal guide inputs improve detail preservation.";

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

[[nodiscard]] bool fill_rgb_buffer(
    const ImagePlane& plane,
    const Box& bounds,
    std::vector<float>& destination,
    bool remap_unsigned_normals,
    const std::function<bool()>& abort_requested) {
    const std::size_t pixel_count =
        static_cast<std::size_t>(bounds.w()) * static_cast<std::size_t>(bounds.h());
    destination.assign(pixel_count * 3U, 0.0F);

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
            destination[pixel * 3U + 0U] = red;
            destination[pixel * 3U + 1U] = green;
            destination[pixel * 3U + 2U] = blue;
        }
    }
    return true;
}

class TempFiles {
public:
    TempFiles() {
        static std::atomic<std::uint64_t> sequence{0};
        const auto id = sequence.fetch_add(1, std::memory_order_relaxed);
        std::filesystem::path root =
            std::filesystem::temp_directory_path() / "hdu-oidn-nuke";
        std::filesystem::create_directories(root);
#ifdef _WIN32
        const std::wstring stem =
            std::to_wstring(GetCurrentProcessId()) + L"-" +
            std::to_wstring(GetCurrentThreadId()) + L"-" + std::to_wstring(id);
#else
        const std::wstring stem = std::to_wstring(id);
#endif
        input = root / (stem + L".input.bin");
        output = root / (stem + L".output.bin");
        log = root / (stem + L".log");
    }

    ~TempFiles() {
        std::error_code error;
        std::filesystem::remove(input, error);
        std::filesystem::remove(output, error);
        std::filesystem::remove(log, error);
    }

    std::filesystem::path input;
    std::filesystem::path output;
    std::filesystem::path log;
};

void write_vector(std::ofstream& stream, const std::vector<float>& values) {
    stream.write(
        reinterpret_cast<const char*>(values.data()),
        static_cast<std::streamsize>(values.size() * sizeof(float)));
    if (!stream) {
        throw std::runtime_error("failed to write OIDN bridge input");
    }
}

void write_bridge_input(
    const std::filesystem::path& path,
    const std::vector<float>& beauty,
    const std::vector<float>* albedo,
    const std::vector<float>* normal,
    unsigned int width,
    unsigned int height,
    int quality,
    bool hdr,
    bool clean_aux) {
    hdu::oidn_bridge::Header header{};
    header.width = width;
    header.height = height;
    header.quality = static_cast<std::uint32_t>(std::clamp(quality, 0, 2));
    if (albedo != nullptr) {
        header.flags |= hdu::oidn_bridge::kHasAlbedo;
    }
    if (normal != nullptr) {
        header.flags |= hdu::oidn_bridge::kHasNormal;
    }
    if (hdr) {
        header.flags |= hdu::oidn_bridge::kHdr;
    }
    if (clean_aux) {
        header.flags |= hdu::oidn_bridge::kCleanAux;
    }

    std::ofstream stream(path, std::ios::binary | std::ios::trunc);
    if (!stream) {
        throw std::runtime_error("could not create OIDN bridge input");
    }
    stream.write(reinterpret_cast<const char*>(&header), sizeof(header));
    write_vector(stream, beauty);
    if (albedo != nullptr) {
        write_vector(stream, *albedo);
    }
    if (normal != nullptr) {
        write_vector(stream, *normal);
    }
}

[[nodiscard]] std::vector<float> read_bridge_output(
    const std::filesystem::path& path,
    std::size_t value_count) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) {
        throw std::runtime_error("OIDN bridge did not create output");
    }
    const auto expected_bytes = static_cast<std::streamoff>(value_count * sizeof(float));
    if (stream.tellg() != expected_bytes) {
        throw std::runtime_error("OIDN bridge output size mismatch");
    }
    stream.seekg(0);
    std::vector<float> output(value_count);
    stream.read(
        reinterpret_cast<char*>(output.data()),
        static_cast<std::streamsize>(expected_bytes));
    if (!stream) {
        throw std::runtime_error("failed to read OIDN bridge output");
    }
    return output;
}

[[nodiscard]] std::string read_log(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        return {};
    }
    std::ostringstream output;
    output << stream.rdbuf();
    return output.str();
}

#ifdef _WIN32

extern "C" IMAGE_DOS_HEADER __ImageBase;

class WinHandle {
public:
    explicit WinHandle(HANDLE handle = nullptr) : handle_(handle) {}
    ~WinHandle() {
        if (handle_ != nullptr && handle_ != INVALID_HANDLE_VALUE) {
            CloseHandle(handle_);
        }
    }
    WinHandle(const WinHandle&) = delete;
    WinHandle& operator=(const WinHandle&) = delete;
    [[nodiscard]] HANDLE get() const { return handle_; }
    [[nodiscard]] HANDLE release() {
        HANDLE handle = handle_;
        handle_ = nullptr;
        return handle;
    }

private:
    HANDLE handle_;
};

[[nodiscard]] std::filesystem::path helper_path() {
    std::vector<wchar_t> buffer(32768);
    const DWORD length = GetModuleFileNameW(
        reinterpret_cast<HMODULE>(&__ImageBase),
        buffer.data(),
        static_cast<DWORD>(buffer.size()));
    if (length == 0 || length == buffer.size()) {
        throw std::runtime_error("could not locate HOidnDenoise plugin directory");
    }
    return std::filesystem::path(std::wstring(buffer.data(), length)).parent_path() /
           "HOidnBridge.exe";
}

[[nodiscard]] std::wstring quote_argument(const std::filesystem::path& value) {
    std::wstring escaped = value.wstring();
    std::wstring result = L"\"";
    for (const wchar_t character : escaped) {
        if (character == L'\"') {
            result += L'\\';
        }
        result += character;
    }
    result += L'\"';
    return result;
}

void run_bridge_process(
    const TempFiles& files,
    int gpu_device,
    const std::function<bool()>& abort_requested) {
    const std::filesystem::path helper = helper_path();
    if (!std::filesystem::is_regular_file(helper)) {
        throw std::runtime_error("HOidnBridge.exe is missing from the plugin package");
    }

    SECURITY_ATTRIBUTES security{};
    security.nLength = sizeof(security);
    security.bInheritHandle = TRUE;
    WinHandle log_handle(CreateFileW(
        files.log.c_str(),
        GENERIC_WRITE,
        FILE_SHARE_READ,
        &security,
        CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        nullptr));
    if (log_handle.get() == INVALID_HANDLE_VALUE) {
        throw std::runtime_error("could not create OIDN bridge log");
    }

    std::wstring command = quote_argument(helper) + L" " +
                           quote_argument(files.input) + L" " +
                           quote_argument(files.output) + L" " +
                           std::to_wstring(gpu_device);
    std::vector<wchar_t> command_buffer(command.begin(), command.end());
    command_buffer.push_back(L'\0');

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = log_handle.get();
    startup.hStdError = log_handle.get();
    PROCESS_INFORMATION process{};
    const std::wstring working_directory = helper.parent_path().wstring();
    const BOOL created = CreateProcessW(
        helper.c_str(),
        command_buffer.data(),
        nullptr,
        nullptr,
        TRUE,
        CREATE_NO_WINDOW,
        nullptr,
        working_directory.c_str(),
        &startup,
        &process);
    if (!created) {
        throw std::runtime_error(
            "could not start HOidnBridge.exe (Windows error " +
            std::to_string(GetLastError()) + ")");
    }

    WinHandle process_handle(process.hProcess);
    WinHandle thread_handle(process.hThread);
    bool cancelled = false;
    while (true) {
        const DWORD wait_result = WaitForSingleObject(process_handle.get(), 50);
        if (wait_result == WAIT_OBJECT_0) {
            break;
        }
        if (wait_result != WAIT_TIMEOUT) {
            TerminateProcess(process_handle.get(), EXIT_FAILURE);
            throw std::runtime_error("waiting for HOidnBridge.exe failed");
        }
        if (abort_requested()) {
            cancelled = true;
            TerminateProcess(process_handle.get(), ERROR_CANCELLED);
            WaitForSingleObject(process_handle.get(), INFINITE);
            break;
        }
    }

    DWORD exit_code = EXIT_FAILURE;
    if (!GetExitCodeProcess(process_handle.get(), &exit_code)) {
        throw std::runtime_error("could not query HOidnBridge.exe exit code");
    }
    HANDLE raw_log_handle = log_handle.release();
    CloseHandle(raw_log_handle);
    if (cancelled) {
        throw std::runtime_error("OIDN render cancelled");
    }
    if (exit_code != EXIT_SUCCESS) {
        const std::string log = read_log(files.log);
        throw std::runtime_error(
            log.empty() ? "HOidnBridge.exe failed" : log);
    }
}

#else

void run_bridge_process(
    const TempFiles&,
    int,
    const std::function<bool()>&) {
    throw std::runtime_error("HOidnDenoise is currently supported on Windows only");
}

#endif

[[nodiscard]] std::vector<float> denoise_with_bridge(
    const std::vector<float>& beauty,
    const std::vector<float>* albedo,
    const std::vector<float>* normal,
    unsigned int width,
    unsigned int height,
    int gpu_device,
    int quality,
    bool hdr,
    bool clean_aux,
    float blend,
    const std::function<bool()>& abort_requested) {
    TempFiles files;
    write_bridge_input(
        files.input,
        beauty,
        albedo,
        normal,
        width,
        height,
        quality,
        hdr,
        clean_aux);
    run_bridge_process(files, gpu_device, abort_requested);
    std::vector<float> output = read_bridge_output(files.output, beauty.size());

    const float input_mix = std::clamp(blend, 0.0F, 1.0F);
    const float denoised_mix = 1.0F - input_mix;
    if (input_mix > 0.0F) {
        for (std::size_t index = 0; index < output.size(); ++index) {
            output[index] = output[index] * denoised_mix + beauty[index] * input_mix;
        }
    }
    return output;
}

class HOidnDenoise final : public PlanarIop {
public:
    explicit HOidnDenoise(Node* node) : PlanarIop(node) {}

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

        Int_knob(callback, &gpu_device_, IRange(0, 15), "gpu_device", "GPU device");
        Tooltip(callback, "Zero-based CUDA device index used by the OIDN helper.");

        static const char* quality_modes[] = {"Fast", "Balanced", "High", nullptr};
        Enumeration_knob(callback, &quality_, quality_modes, "quality", "quality");
        Tooltip(callback, "OIDN quality and performance mode.");

        Bool_knob(callback, &hdr_, "hdr", "HDR input");
        Tooltip(callback, "Enable for HDR beauty renders.");

        Bool_knob(callback, &clean_aux_, "clean_aux", "clean auxiliary passes");
        Tooltip(callback, "Enable when albedo and normal guides are noise-free.");

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
            "Select Unsigned only when the normal pass is stored in the 0-to-1 range.");

        Bool_knob(
            callback,
            &passthrough_on_error_,
            "passthrough_on_error",
            "passthrough on error");
        Tooltip(
            callback,
            "Return the beauty input unchanged if OIDN fails instead of failing the render.");

        Text_knob(
            callback,
            (std::string("h_denoise_utils ") + HDU_VERSION +
             " | Intel Open Image Denoise CUDA helper")
                .c_str());
    }

    void _validate(bool for_real) override {
        copy_info();
        set_out_channels(input0().info().channels());

        if (input(2) != nullptr && input(1) == nullptr) {
            error("HOidnDenoise: the normal guide requires an albedo guide");
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
                    "HOidnDenoise: %s must match the beauty format and data window",
                    input_index == 1 ? "albedo" : "normal");
            }

            const ChannelSet guide_channels = guide_info.channels();
            if (!guide_channels.contains(Chan_Red) ||
                !guide_channels.contains(Chan_Green) ||
                !guide_channels.contains(Chan_Blue)) {
                error(
                    "HOidnDenoise: %s must provide red, green, and blue channels",
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

        for (int input_index = 1; input_index <= 2; ++input_index) {
            if (input(input_index) == nullptr) {
                continue;
            }
            ChannelSet guide_channels = Mask_RGB;
            guide_channels &= input(input_index)->info().channels();
            requests.request(input(input_index), box, guide_channels, count);
        }
    }

    void renderStripe(ImagePlane& output_plane) override {
        const Box bounds = output_plane.bounds();
        ChannelSet rgb_intersection = output_plane.channels();
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
            const std::function<bool()> abort_requested = [this] { return aborted(); };

            ChannelSet beauty_channels = available_channels(input0(), Mask_RGBA);
            ImagePlane beauty_plane(bounds, true, beauty_channels);
            input0().fetchPlane(beauty_plane);

            std::vector<float> beauty_pixels;
            if (!fill_rgb_buffer(
                    beauty_plane,
                    bounds,
                    beauty_pixels,
                    false,
                    abort_requested)) {
                passthrough(output_plane);
                return;
            }

            std::vector<float> albedo_pixels;
            std::vector<float> normal_pixels;
            const std::vector<float>* albedo_ptr = nullptr;
            const std::vector<float>* normal_ptr = nullptr;

            if (input(1) != nullptr) {
                ChannelSet channels = available_channels(*input(1), Mask_RGB);
                ImagePlane albedo_plane(bounds, true, channels);
                input(1)->fetchPlane(albedo_plane);
                if (!fill_rgb_buffer(
                        albedo_plane,
                        bounds,
                        albedo_pixels,
                        false,
                        abort_requested)) {
                    passthrough(output_plane);
                    return;
                }
                albedo_ptr = &albedo_pixels;
            }

            if (input(2) != nullptr) {
                ChannelSet channels = available_channels(*input(2), Mask_RGB);
                ImagePlane normal_plane(bounds, true, channels);
                input(2)->fetchPlane(normal_plane);
                if (!fill_rgb_buffer(
                        normal_plane,
                        bounds,
                        normal_pixels,
                        normal_encoding_ == 1,
                        abort_requested)) {
                    passthrough(output_plane);
                    return;
                }
                normal_ptr = &normal_pixels;
            }

            std::vector<float> output_pixels = denoise_with_bridge(
                beauty_pixels,
                albedo_ptr,
                normal_ptr,
                static_cast<unsigned int>(bounds.w()),
                static_cast<unsigned int>(bounds.h()),
                gpu_device_,
                quality_,
                hdr_,
                clean_aux_,
                blend_factor_,
                abort_requested);

            if (aborted()) {
                passthrough(output_plane);
                return;
            }
            if (!write_output(output_plane, beauty_plane, output_pixels, abort_requested)) {
                passthrough(output_plane);
            }
        } catch (const std::exception& exception) {
            if (aborted()) {
                passthrough(output_plane);
                return;
            }
            if (passthrough_on_error_) {
                warning("HOidnDenoise: %s", exception.what());
                passthrough(output_plane);
                return;
            }
            error("HOidnDenoise: %s", exception.what());
            output_plane.makeWritable();
            for (Channel channel = output_plane.channels().first();
                 channel != Chan_Black;
                 channel = output_plane.channels().next(channel)) {
                output_plane.fillChannelThreaded(channel, 0.0F);
            }
        }
    }

private:
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
                        value = denoised_pixels[pixel * 3U + 0U];
                    } else if (channel == Chan_Green) {
                        value = denoised_pixels[pixel * 3U + 1U];
                    } else if (channel == Chan_Blue) {
                        value = denoised_pixels[pixel * 3U + 2U];
                    }
                    output_plane.writableAt(x, y, output_channel) = value;
                }
            }
        }
        return true;
    }

    float blend_factor_ = 0.0F;
    int gpu_device_ = 0;
    int quality_ = 2;
    bool hdr_ = true;
    bool clean_aux_ = true;
    int normal_encoding_ = 0;
    bool passthrough_on_error_ = true;
};

Op* build(Node* node) {
    return new HOidnDenoise(node);
}

const Iop::Description description(kClass, build);

}  // namespace
