#include "oidn_bridge_protocol.h"

#include <OpenImageDenoise/oidn.hpp>

#ifdef _WIN32
#include <Windows.h>
#endif

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using hdu::oidn_bridge::Header;

[[noreturn]] void throw_oidn_error(oidn::DeviceRef& device, const char* context) {
    const char* message = nullptr;
    const oidn::Error error = device.getError(message);
    if (error == oidn::Error::None) {
        throw std::runtime_error(std::string(context) + ": unknown OIDN error");
    }
    throw std::runtime_error(
        std::string(context) + ": " + (message != nullptr ? message : "unknown error"));
}

void check_oidn_error(oidn::DeviceRef& device, const char* context) {
    const char* message = nullptr;
    const oidn::Error error = device.getError(message);
    if (error != oidn::Error::None) {
        throw std::runtime_error(
            std::string(context) + ": " + (message != nullptr ? message : "unknown error"));
    }
}

[[nodiscard]] oidn::Quality quality_from_value(std::uint32_t quality) {
    switch (quality) {
        case 0:
            return oidn::Quality::Fast;
        case 1:
            return oidn::Quality::Balanced;
        default:
            return oidn::Quality::High;
    }
}

template<typename T>
void read_exact(std::ifstream& stream, T* data, std::size_t count, const char* label) {
    const auto bytes = static_cast<std::streamsize>(count * sizeof(T));
    stream.read(reinterpret_cast<char*>(data), bytes);
    if (stream.gcount() != bytes) {
        throw std::runtime_error(std::string("truncated OIDN bridge ") + label);
    }
}

void write_exact(
    std::ofstream& stream,
    const float* data,
    std::size_t count,
    const char* label) {
    const auto bytes = static_cast<std::streamsize>(count * sizeof(float));
    stream.write(reinterpret_cast<const char*>(data), bytes);
    if (!stream) {
        throw std::runtime_error(std::string("failed to write OIDN bridge ") + label);
    }
}

int run(const std::filesystem::path& input_path, const std::filesystem::path& output_path) {
    std::ifstream input(input_path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("could not open OIDN bridge input");
    }

    Header header{};
    read_exact(input, &header, 1, "header");
    if (header.magic != hdu::oidn_bridge::kMagic ||
        header.version != hdu::oidn_bridge::kVersion ||
        header.width == 0 || header.height == 0) {
        throw std::runtime_error("invalid OIDN bridge header");
    }

    const std::size_t pixel_count =
        static_cast<std::size_t>(header.width) * static_cast<std::size_t>(header.height);
    const std::size_t value_count = pixel_count * 3U;
    const std::size_t byte_count = value_count * sizeof(float);
    const bool has_albedo = (header.flags & hdu::oidn_bridge::kHasAlbedo) != 0U;
    const bool has_normal = (header.flags & hdu::oidn_bridge::kHasNormal) != 0U;
    if (has_normal && !has_albedo) {
        throw std::runtime_error("normal guide requires albedo guide");
    }

    std::vector<float> beauty(value_count);
    std::vector<float> albedo(has_albedo ? value_count : 0U);
    std::vector<float> normal(has_normal ? value_count : 0U);
    std::vector<float> output(value_count);
    read_exact(input, beauty.data(), beauty.size(), "beauty buffer");
    if (has_albedo) {
        read_exact(input, albedo.data(), albedo.size(), "albedo buffer");
    }
    if (has_normal) {
        read_exact(input, normal.data(), normal.size(), "normal buffer");
    }

    oidn::DeviceRef device = oidn::newDevice(oidn::DeviceType::CUDA);
    if (!device) {
        const char* message = nullptr;
        oidn::getError(message);
        throw std::runtime_error(
            std::string("creating OIDN CUDA device: ") +
            (message != nullptr ? message : "unknown error"));
    }
    device.commit();
    check_oidn_error(device, "committing OIDN CUDA device");

    oidn::BufferRef color_buffer = device.newBuffer(byte_count);
    oidn::BufferRef output_buffer = device.newBuffer(byte_count);
    oidn::BufferRef albedo_buffer = has_albedo ? device.newBuffer(byte_count) : oidn::BufferRef{};
    oidn::BufferRef normal_buffer = has_normal ? device.newBuffer(byte_count) : oidn::BufferRef{};
    check_oidn_error(device, "allocating OIDN buffers");

    color_buffer.write(0, byte_count, beauty.data());
    if (has_albedo) {
        albedo_buffer.write(0, byte_count, albedo.data());
    }
    if (has_normal) {
        normal_buffer.write(0, byte_count, normal.data());
    }
    check_oidn_error(device, "copying OIDN input buffers");

    oidn::FilterRef filter = device.newFilter("RT");
    if (!filter) {
        throw_oidn_error(device, "creating OIDN RT filter");
    }
    filter.setImage(
        "color", color_buffer, oidn::Format::Float3, header.width, header.height);
    if (has_albedo) {
        filter.setImage(
            "albedo", albedo_buffer, oidn::Format::Float3, header.width, header.height);
    }
    if (has_normal) {
        filter.setImage(
            "normal", normal_buffer, oidn::Format::Float3, header.width, header.height);
    }
    filter.setImage(
        "output", output_buffer, oidn::Format::Float3, header.width, header.height);
    filter.set("hdr", (header.flags & hdu::oidn_bridge::kHdr) != 0U);
    filter.set("cleanAux", (header.flags & hdu::oidn_bridge::kCleanAux) != 0U);
    filter.set("quality", quality_from_value(header.quality));
    filter.commit();
    check_oidn_error(device, "committing OIDN filter");
    filter.execute();
    check_oidn_error(device, "executing OIDN filter");

    output_buffer.read(0, byte_count, output.data());
    device.sync();
    check_oidn_error(device, "reading OIDN output buffer");

    std::ofstream output_file(output_path, std::ios::binary | std::ios::trunc);
    if (!output_file) {
        throw std::runtime_error("could not create OIDN bridge output");
    }
    write_exact(output_file, output.data(), output.size(), "output buffer");
    return EXIT_SUCCESS;
}

}  // namespace

int main(int argc, char* argv[]) {
#ifdef _WIN32
    if (!SetDllDirectoryW(L"")) {
        std::cerr << "HOidnBridge: failed to clear inherited DLL directory\n";
        return EXIT_FAILURE;
    }
    if (!SetDefaultDllDirectories(
            LOAD_LIBRARY_SEARCH_APPLICATION_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32)) {
        std::cerr << "HOidnBridge: failed to configure DLL search path\n";
        return EXIT_FAILURE;
    }
#endif
    if (argc != 4) {
        std::cerr << "usage: HOidnBridge.exe <input.bin> <output.bin> <gpu-index>\n";
        return EXIT_FAILURE;
    }

    try {
        const int gpu_index = std::stoi(argv[3]);
        if (gpu_index < 0) {
            throw std::runtime_error("GPU index must be non-negative");
        }
#ifdef _WIN32
        if (_putenv_s("CUDA_VISIBLE_DEVICES", std::to_string(gpu_index).c_str()) != 0) {
            throw std::runtime_error("failed to set CUDA_VISIBLE_DEVICES");
        }
#else
        if (setenv("CUDA_VISIBLE_DEVICES", std::to_string(gpu_index).c_str(), 1) != 0) {
            throw std::runtime_error("failed to set CUDA_VISIBLE_DEVICES");
        }
#endif
        return run(argv[1], argv[2]);
    } catch (const std::exception& error) {
        std::cerr << "HOidnBridge: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
