#include <OpenImageDenoise/oidn.hpp>
#include <OpenImageIO/imagebuf.h>
#include <OpenImageIO/imageio.h>

#include <ImfChannelList.h>
#include <ImfFrameBuffer.h>
#include <ImfHeader.h>
#include <ImfMultiPartInputFile.h>
#include <ImfMultiPartOutputFile.h>
#include <ImfOutputPart.h>
#include <ImfPartType.h>
#include <half.h>

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <vector>

#define DENOISER_MAJOR_VERSION 1
#define DENOISER_MINOR_VERSION 0

namespace
{
int g_verbosity = 1;
std::chrono::high_resolution_clock::time_point g_app_start_time;

struct SubimageInfo
{
    int index = 0;
    std::string name;
    OIIO::ImageSpec spec;
};

struct MultipartOptions
{
    bool enabled = false;
    std::string filename;
    std::string output_filename;
    std::string beauty_name = "C";
    std::string albedo_name = "albedo";
    std::string normal_name = "N";
    std::map<int, std::string> aov_names;
    std::vector<SubimageInfo> subimages;
};

struct NativeEXRPlane
{
    std::vector<unsigned char> pixels;
    std::vector<size_t> channel_offsets;
    size_t pixel_stride = 0;
};

struct PlanePixels
{
    SubimageInfo subimage;
    std::vector<float> pixels;
};

std::string getTime()
{
    const auto elapsed = std::chrono::high_resolution_clock::now() - g_app_start_time;
    double milliseconds = std::chrono::duration<double, std::milli>(elapsed).count();
    int seconds = static_cast<int>(milliseconds / 1000.0);
    const int minutes = seconds / 60;
    milliseconds -= seconds * 1000.0;
    seconds -= minutes * 60;

    char value[16];
    std::snprintf(value, sizeof(value), "%02d:%02d:%03d", minutes, seconds, static_cast<int>(milliseconds));
    return std::string(value);
}

template <typename... Args>
void PrintInfo(const char* format, Args... args)
{
    if (!g_verbosity)
        return;

    char buffer[1024];
    std::snprintf(buffer, sizeof(buffer), format, args...);
    std::cout << getTime() << "         | " << buffer << std::endl;
}

template <typename... Args>
void PrintWarning(const char* format, Args... args)
{
    char buffer[1024];
    std::snprintf(buffer, sizeof(buffer), format, args...);
    std::cerr << getTime() << " WARNING | " << buffer << std::endl;
}

template <typename... Args>
void PrintError(const char* format, Args... args)
{
    char buffer[1024];
    std::snprintf(buffer, sizeof(buffer), format, args...);
    std::cerr << getTime() << " ERROR   | " << buffer << std::endl;
}

std::string toLower(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

bool startsWith(const std::string& value, const std::string& prefix)
{
    return value.rfind(prefix, 0) == 0;
}

bool endsWith(const std::string& value, const std::string& suffix)
{
    if (suffix.size() > value.size())
        return false;
    return std::equal(suffix.rbegin(), suffix.rend(), value.rbegin());
}

bool consumeValue(int argc, char* argv[], int& index, const std::string& flag, std::string& value)
{
    ++index;
    if (index >= argc)
    {
        PrintError("incorrect number of arguments for flag %s", flag.c_str());
        return false;
    }
    value = argv[index];
    return true;
}

std::string subimageName(const OIIO::ImageSpec& spec, int index)
{
    std::string name = spec.get_string_attribute("name");
    if (!name.empty())
        return name;
    return "subimage_" + std::to_string(index);
}

size_t exrChannelSize(OPENEXR_IMF_NAMESPACE::PixelType type)
{
    switch (type)
    {
    case OPENEXR_IMF_NAMESPACE::HALF:
        return sizeof(IMATH_NAMESPACE::half);
    case OPENEXR_IMF_NAMESPACE::FLOAT:
        return sizeof(float);
    case OPENEXR_IMF_NAMESPACE::UINT:
        return sizeof(unsigned int);
    default:
        return 0;
    }
}

int findExactChannelIndex(const OIIO::ImageSpec& spec, const std::string& channel_name)
{
    for (int i = 0; i < static_cast<int>(spec.channelnames.size()); ++i)
    {
        if (spec.channelnames[static_cast<size_t>(i)] == channel_name)
            return i;
    }
    return -1;
}

int findHeaderChannelIndex(const OIIO::ImageSpec& spec, const char* channel_name)
{
    const std::string desired(channel_name);
    const int exact = findExactChannelIndex(spec, desired);
    if (exact >= 0)
        return exact;

    const std::string lower_desired = toLower(desired);
    for (int i = 0; i < static_cast<int>(spec.channelnames.size()); ++i)
    {
        if (toLower(spec.channelnames[static_cast<size_t>(i)]) == lower_desired)
            return i;
    }

    const size_t dot = desired.rfind('.');
    if (dot != std::string::npos && dot + 1 < desired.size())
    {
        const std::string suffix = desired.substr(dot + 1);
        const std::string lower_suffix = toLower(suffix);
        for (int i = 0; i < static_cast<int>(spec.channelnames.size()); ++i)
        {
            if (toLower(spec.channelnames[static_cast<size_t>(i)]) == lower_suffix)
                return i;
        }
    }

    return -1;
}

int findRGBChannelIndex(const OIIO::ImageSpec& spec, const std::string& part_name, const std::string& component)
{
    const std::vector<std::string> candidates = {
        component,
        toLower(component),
        part_name + "." + component,
        part_name + "." + toLower(component),
    };

    for (const auto& candidate : candidates)
    {
        const int exact = findExactChannelIndex(spec, candidate);
        if (exact >= 0)
            return exact;
    }

    const std::string lower_component = toLower(component);
    const std::string lower_suffix = "." + lower_component;
    for (int i = 0; i < static_cast<int>(spec.channelnames.size()); ++i)
    {
        const std::string lower_name = toLower(spec.channelnames[static_cast<size_t>(i)]);
        if (lower_name == lower_component || endsWith(lower_name, lower_suffix))
            return i;
    }

    return -1;
}

bool findRGBChannels(const SubimageInfo& subimage, int rgb[3])
{
    rgb[0] = findRGBChannelIndex(subimage.spec, subimage.name, "R");
    rgb[1] = findRGBChannelIndex(subimage.spec, subimage.name, "G");
    rgb[2] = findRGBChannelIndex(subimage.spec, subimage.name, "B");

    if (rgb[0] < 0 || rgb[1] < 0 || rgb[2] < 0)
    {
        PrintError("Subimage '%s' does not expose RGB channels required by OIDN", subimage.name.c_str());
        return false;
    }
    return true;
}

bool loadMultipartLayout(MultipartOptions& multipart)
{
    auto input = OIIO::ImageInput::open(multipart.filename);
    if (!input)
    {
        PrintError("Could not open multipart input %s", multipart.filename.c_str());
        PrintError("[OIIO]: %s", OIIO::geterror().c_str());
        return false;
    }

    multipart.subimages.clear();
    for (int subimage = 0; input->seek_subimage(subimage, 0); ++subimage)
    {
        const OIIO::ImageSpec& spec = input->spec();
        multipart.subimages.push_back(SubimageInfo{subimage, subimageName(spec, subimage), spec});
    }
    input->close();

    if (multipart.subimages.empty())
    {
        PrintError("No subimages found in multipart input %s", multipart.filename.c_str());
        return false;
    }
    return true;
}

const SubimageInfo* findMultipartSubimage(const MultipartOptions& multipart, const std::string& name)
{
    const std::string desired = toLower(name);
    for (const auto& subimage : multipart.subimages)
    {
        if (toLower(subimage.name) == desired)
            return &subimage;
    }
    return nullptr;
}

bool readMultipartSourcePlane(const MultipartOptions& multipart, const SubimageInfo& subimage, std::vector<float>& pixels)
{
    OIIO::ImageBuf source_plane(multipart.filename, subimage.index, 0);
    if (!source_plane.init_spec(multipart.filename, subimage.index, 0))
    {
        PrintError("Could not load subimage %d from %s", subimage.index, multipart.filename.c_str());
        PrintError("[OIIO]: %s", source_plane.geterror().c_str());
        return false;
    }

    const OIIO::ROI roi = OIIO::get_roi_full(source_plane.spec());
    pixels.resize(static_cast<size_t>(roi.width()) * static_cast<size_t>(roi.height()) * static_cast<size_t>(roi.nchannels()));
    if (!source_plane.get_pixels(roi, OIIO::TypeDesc::FLOAT, pixels.data()))
    {
        PrintError("Could not read subimage %d from %s", subimage.index, multipart.filename.c_str());
        PrintError("[OIIO]: %s", source_plane.geterror().c_str());
        return false;
    }
    return true;
}

bool loadPlaneByName(const MultipartOptions& multipart, const std::string& name, PlanePixels& plane, const char* label)
{
    const SubimageInfo* subimage = findMultipartSubimage(multipart, name);
    if (!subimage)
    {
        PrintError("Could not find %s subimage '%s' in %s", label, name.c_str(), multipart.filename.c_str());
        return false;
    }

    plane.subimage = *subimage;
    if (!readMultipartSourcePlane(multipart, plane.subimage, plane.pixels))
        return false;

    if (g_verbosity >= 2)
        PrintInfo("Loaded %s subimage '%s' at index %d", label, name.c_str(), subimage->index);
    return true;
}

bool packNativeEXRPlane(
    const std::vector<float>& source_pixels,
    const OIIO::ImageSpec& spec,
    const OPENEXR_IMF_NAMESPACE::Header& header,
    NativeEXRPlane& native_plane)
{
    const IMATH_NAMESPACE::Box2i data_window = header.dataWindow();
    const size_t width = static_cast<size_t>(data_window.max.x - data_window.min.x + 1);
    const size_t height = static_cast<size_t>(data_window.max.y - data_window.min.y + 1);
    const size_t expected_values = width * height * static_cast<size_t>(spec.nchannels);
    if (source_pixels.size() != expected_values)
    {
        const std::string spec_name(spec.get_string_attribute("name"));
        PrintError("Pixel buffer size mismatch for subimage '%s': expected %zu values, got %zu",
            spec_name.c_str(), expected_values, source_pixels.size());
        return false;
    }

    native_plane = NativeEXRPlane();
    const OPENEXR_IMF_NAMESPACE::ChannelList& channels = header.channels();
    for (OPENEXR_IMF_NAMESPACE::ChannelList::ConstIterator it = channels.begin(); it != channels.end(); ++it)
    {
        const size_t channel_size = exrChannelSize(it.channel().type);
        if (!channel_size)
        {
            PrintError("Unsupported OpenEXR channel type in '%s'", it.name());
            return false;
        }
        if (it.channel().xSampling != 1 || it.channel().ySampling != 1)
        {
            PrintError("Unsupported subsampled OpenEXR channel '%s'", it.name());
            return false;
        }
        native_plane.channel_offsets.push_back(native_plane.pixel_stride);
        native_plane.pixel_stride += channel_size;
    }

    native_plane.pixels.resize(width * height * native_plane.pixel_stride);
    size_t header_channel = 0;
    for (OPENEXR_IMF_NAMESPACE::ChannelList::ConstIterator it = channels.begin(); it != channels.end(); ++it, ++header_channel)
    {
        const int source_channel = findHeaderChannelIndex(spec, it.name());
        if (source_channel < 0)
        {
            PrintError("Could not map OpenEXR channel '%s' to OIIO subimage channels", it.name());
            return false;
        }

        const size_t channel_offset = native_plane.channel_offsets[header_channel];
        for (size_t pixel = 0; pixel < width * height; ++pixel)
        {
            const float value = source_pixels[pixel * static_cast<size_t>(spec.nchannels) + static_cast<size_t>(source_channel)];
            unsigned char* destination = native_plane.pixels.data() + pixel * native_plane.pixel_stride + channel_offset;
            switch (it.channel().type)
            {
            case OPENEXR_IMF_NAMESPACE::HALF:
            {
                IMATH_NAMESPACE::half half_value(value);
                std::memcpy(destination, &half_value, sizeof(half_value));
                break;
            }
            case OPENEXR_IMF_NAMESPACE::FLOAT:
                std::memcpy(destination, &value, sizeof(value));
                break;
            case OPENEXR_IMF_NAMESPACE::UINT:
            {
                const unsigned int uint_value = value <= 0.0f ? 0u : static_cast<unsigned int>(value);
                std::memcpy(destination, &uint_value, sizeof(uint_value));
                break;
            }
            default:
                return false;
            }
        }
    }

    return true;
}

bool writeNativeEXRPart(
    OPENEXR_IMF_NAMESPACE::MultiPartOutputFile& output,
    int output_part,
    const OPENEXR_IMF_NAMESPACE::Header& header,
    const OIIO::ImageSpec& spec,
    const std::vector<float>& pixels)
{
    NativeEXRPlane native_plane;
    if (!packNativeEXRPlane(pixels, spec, header, native_plane))
        return false;

    const IMATH_NAMESPACE::Box2i data_window = header.dataWindow();
    const int width = data_window.max.x - data_window.min.x + 1;
    const int height = data_window.max.y - data_window.min.y + 1;
    const size_t row_stride = native_plane.pixel_stride * static_cast<size_t>(width);

    OPENEXR_IMF_NAMESPACE::FrameBuffer frame_buffer;
    size_t channel = 0;
    for (OPENEXR_IMF_NAMESPACE::ChannelList::ConstIterator it = header.channels().begin(); it != header.channels().end(); ++it, ++channel)
    {
        char* base = reinterpret_cast<char*>(native_plane.pixels.data() + native_plane.channel_offsets[channel]);
        base -= static_cast<ptrdiff_t>(data_window.min.x) * static_cast<ptrdiff_t>(native_plane.pixel_stride);
        base -= static_cast<ptrdiff_t>(data_window.min.y) * static_cast<ptrdiff_t>(row_stride);
        frame_buffer.insert(
            it.name(),
            OPENEXR_IMF_NAMESPACE::Slice(
                it.channel().type,
                base,
                native_plane.pixel_stride,
                row_stride,
                it.channel().xSampling,
                it.channel().ySampling));
    }

    OPENEXR_IMF_NAMESPACE::OutputPart part(output, output_part);
    part.setFrameBuffer(frame_buffer);
    part.writePixels(height);
    return true;
}

bool writeMultipartOutput(
    const MultipartOptions& multipart,
    const std::string& out_path,
    const std::map<int, std::vector<float>>& replacements)
{
    try
    {
        OPENEXR_IMF_NAMESPACE::MultiPartInputFile source_file(multipart.filename.c_str());
        if (source_file.parts() != static_cast<int>(multipart.subimages.size()))
        {
            PrintError("OpenEXR part count mismatch for %s", multipart.filename.c_str());
            return false;
        }

        std::vector<OPENEXR_IMF_NAMESPACE::Header> headers;
        headers.reserve(multipart.subimages.size());
        for (const auto& subimage : multipart.subimages)
        {
            const OPENEXR_IMF_NAMESPACE::Header& header = source_file.header(subimage.index);
            if (std::string(header.type()) != OPENEXR_IMF_NAMESPACE::SCANLINEIMAGE)
            {
                PrintError("Only scanline multipart OpenEXR parts are supported for metadata-preserving output");
                return false;
            }
            headers.push_back(header);
        }

        OPENEXR_IMF_NAMESPACE::MultiPartOutputFile output(
            out_path.c_str(),
            headers.data(),
            static_cast<int>(headers.size()));

        int output_part = 0;
        for (const auto& subimage : multipart.subimages)
        {
            const auto replacement = replacements.find(subimage.index);
            if (replacement != replacements.end())
            {
                if (!writeNativeEXRPart(output, output_part, headers[static_cast<size_t>(output_part)], subimage.spec, replacement->second))
                {
                    PrintError("Could not write denoised subimage %d to %s", subimage.index, out_path.c_str());
                    return false;
                }
            }
            else
            {
                std::vector<float> source_pixels;
                if (!readMultipartSourcePlane(multipart, subimage, source_pixels))
                    return false;

                if (!writeNativeEXRPart(output, output_part, headers[static_cast<size_t>(output_part)], subimage.spec, source_pixels))
                {
                    PrintError("Could not write unchanged subimage %d to %s", subimage.index, out_path.c_str());
                    return false;
                }
            }
            ++output_part;
        }
    }
    catch (const std::exception& e)
    {
        PrintError("OpenEXR multipart write failed for %s: %s", out_path.c_str(), e.what());
        return false;
    }

    return true;
}

size_t planeWidth(const SubimageInfo& subimage)
{
    return static_cast<size_t>(subimage.spec.width);
}

size_t planeHeight(const SubimageInfo& subimage)
{
    return static_cast<size_t>(subimage.spec.height);
}

bool extractRGB(const PlanePixels& plane, std::vector<float>& rgb)
{
    int channels[3];
    if (!findRGBChannels(plane.subimage, channels))
        return false;

    const size_t width = planeWidth(plane.subimage);
    const size_t height = planeHeight(plane.subimage);
    const size_t pixel_count = width * height;
    const size_t channel_count = static_cast<size_t>(plane.subimage.spec.nchannels);
    rgb.resize(pixel_count * 3);

    for (size_t pixel = 0; pixel < pixel_count; ++pixel)
    {
        const size_t source = pixel * channel_count;
        const size_t target = pixel * 3;
        rgb[target + 0] = plane.pixels[source + static_cast<size_t>(channels[0])];
        rgb[target + 1] = plane.pixels[source + static_cast<size_t>(channels[1])];
        rgb[target + 2] = plane.pixels[source + static_cast<size_t>(channels[2])];
    }

    return true;
}

bool injectRGB(PlanePixels& plane, const std::vector<float>& rgb)
{
    int channels[3];
    if (!findRGBChannels(plane.subimage, channels))
        return false;

    const size_t width = planeWidth(plane.subimage);
    const size_t height = planeHeight(plane.subimage);
    const size_t pixel_count = width * height;
    const size_t channel_count = static_cast<size_t>(plane.subimage.spec.nchannels);
    if (rgb.size() != pixel_count * 3)
    {
        PrintError("Denoised RGB buffer size mismatch for '%s'", plane.subimage.name.c_str());
        return false;
    }

    for (size_t pixel = 0; pixel < pixel_count; ++pixel)
    {
        const size_t target = pixel * channel_count;
        const size_t source = pixel * 3;
        plane.pixels[target + static_cast<size_t>(channels[0])] = rgb[source + 0];
        plane.pixels[target + static_cast<size_t>(channels[1])] = rgb[source + 1];
        plane.pixels[target + static_cast<size_t>(channels[2])] = rgb[source + 2];
    }

    return true;
}

bool sameDimensions(const PlanePixels& left, const PlanePixels& right)
{
    return planeWidth(left.subimage) == planeWidth(right.subimage)
        && planeHeight(left.subimage) == planeHeight(right.subimage);
}

bool denoisePlane(
    oidn::DeviceRef& device,
    PlanePixels& target,
    const PlanePixels* albedo,
    const PlanePixels* normal)
{
    std::vector<float> color;
    if (!extractRGB(target, color))
        return false;

    std::vector<float> output(color.size());
    std::vector<float> albedo_rgb;
    std::vector<float> normal_rgb;

    if (albedo)
    {
        if (!sameDimensions(target, *albedo))
        {
            PrintError("Albedo subimage '%s' is not the same resolution as target '%s'",
                albedo->subimage.name.c_str(), target.subimage.name.c_str());
            return false;
        }
        if (!extractRGB(*albedo, albedo_rgb))
            return false;
    }

    if (normal)
    {
        if (!sameDimensions(target, *normal))
        {
            PrintError("Normal subimage '%s' is not the same resolution as target '%s'",
                normal->subimage.name.c_str(), target.subimage.name.c_str());
            return false;
        }
        if (!extractRGB(*normal, normal_rgb))
            return false;
    }

    oidn::FilterRef filter = device.newFilter("RT");
    const size_t width = planeWidth(target.subimage);
    const size_t height = planeHeight(target.subimage);
    filter.setImage("color", color.data(), oidn::Format::Float3, width, height);
    if (albedo)
        filter.setImage("albedo", albedo_rgb.data(), oidn::Format::Float3, width, height);
    if (normal)
        filter.setImage("normal", normal_rgb.data(), oidn::Format::Float3, width, height);
    filter.setImage("output", output.data(), oidn::Format::Float3, width, height);
    filter.set("hdr", true);
    filter.set("cleanAux", true);
    filter.set("quality", oidn::Quality::High);

    filter.commit();
    filter.execute();

    const char* message = nullptr;
    const oidn::Error error = device.getError(message);
    if (error != oidn::Error::None)
    {
        PrintError("OIDN failed while denoising '%s': %s", target.subimage.name.c_str(), message ? message : "unknown error");
        return false;
    }

    return injectRGB(target, output);
}

void printParams()
{
    const int old_verbosity = g_verbosity;
    g_verbosity = 1;
    PrintInfo("Command line parameters");
    PrintInfo("-v [int]                : log verbosity level 0:disabled 1:simple 2:full (default 1)");
    PrintInfo("-multipart [string]     : path to multipart EXR input; loads planes by subimage name");
    PrintInfo("-o [string]             : path to output image");
    PrintInfo("-beauty-name [string]   : beauty subimage name for -multipart (default C)");
    PrintInfo("-albedo-name [string]   : albedo subimage name for -multipart (default albedo)");
    PrintInfo("-normal-name [string]   : normal subimage name for -multipart (default N)");
    PrintInfo("-aov-nameN [string]     : additional multipart AOV subimage name to denoise");
    g_verbosity = old_verbosity;
}
}

int main(int argc, char* argv[])
{
    g_app_start_time = std::chrono::high_resolution_clock::now();
    MultipartOptions multipart;

    for (int i = 1; i < argc; ++i)
    {
        const std::string arg(argv[i]);
        std::string value;

        if (arg == "-v")
        {
            if (!consumeValue(argc, argv, i, arg, value))
                return EXIT_FAILURE;
            g_verbosity = std::stoi(value);
        }
    }

    PrintInfo("Launching HDU OIDN Denoiser command line app v%d.%d", DENOISER_MAJOR_VERSION, DENOISER_MINOR_VERSION);

    if (argc == 1)
    {
        printParams();
        return EXIT_SUCCESS;
    }

    for (int i = 1; i < argc; ++i)
    {
        const std::string arg(argv[i]);
        std::string value;

        if (arg == "-h" || arg == "--help")
        {
            printParams();
            return EXIT_SUCCESS;
        }
        if (arg == "-v")
        {
            if (!consumeValue(argc, argv, i, arg, value))
                return EXIT_FAILURE;
            continue;
        }
        if (arg == "-multipart")
        {
            if (!consumeValue(argc, argv, i, arg, value))
                return EXIT_FAILURE;
            multipart.enabled = true;
            multipart.filename = value;
            continue;
        }
        if (arg == "-o")
        {
            if (!consumeValue(argc, argv, i, arg, value))
                return EXIT_FAILURE;
            multipart.output_filename = value;
            continue;
        }
        if (arg == "-beauty-name")
        {
            if (!consumeValue(argc, argv, i, arg, value))
                return EXIT_FAILURE;
            multipart.beauty_name = value;
            continue;
        }
        if (arg == "-albedo-name")
        {
            if (!consumeValue(argc, argv, i, arg, value))
                return EXIT_FAILURE;
            multipart.albedo_name = value;
            continue;
        }
        if (arg == "-normal-name")
        {
            if (!consumeValue(argc, argv, i, arg, value))
                return EXIT_FAILURE;
            multipart.normal_name = value;
            continue;
        }
        if (startsWith(arg, "-aov-name"))
        {
            if (arg.size() == 9)
            {
                PrintError("-aov-name parameter requires number id such as -aov-name0");
                return EXIT_FAILURE;
            }
            if (!consumeValue(argc, argv, i, arg, value))
                return EXIT_FAILURE;
            multipart.aov_names[std::stoi(arg.substr(9))] = value;
            continue;
        }

        PrintError("Unsupported argument for OIDN multipart wrapper: %s", arg.c_str());
        return EXIT_FAILURE;
    }

    if (!multipart.enabled)
    {
        PrintError("The HDU OIDN wrapper currently requires -multipart input");
        return EXIT_FAILURE;
    }
    if (multipart.output_filename.empty())
    {
        PrintError("No output file set; use -o");
        return EXIT_FAILURE;
    }
    if (!loadMultipartLayout(multipart))
        return EXIT_FAILURE;

    PlanePixels albedo;
    PlanePixels normal;
    PlanePixels* albedo_ptr = nullptr;
    PlanePixels* normal_ptr = nullptr;

    if (findMultipartSubimage(multipart, multipart.albedo_name))
    {
        if (!loadPlaneByName(multipart, multipart.albedo_name, albedo, "albedo"))
            return EXIT_FAILURE;
        albedo_ptr = &albedo;
    }
    else
    {
        PrintWarning("Multipart albedo subimage '%s' was not found; denoising without albedo guide", multipart.albedo_name.c_str());
    }

    if (findMultipartSubimage(multipart, multipart.normal_name))
    {
        if (!loadPlaneByName(multipart, multipart.normal_name, normal, "normal"))
            return EXIT_FAILURE;
        normal_ptr = &normal;
    }
    else
    {
        PrintWarning("Multipart normal subimage '%s' was not found; denoising without normal guide", multipart.normal_name.c_str());
    }

    oidn::DeviceRef device = oidn::newDevice(oidn::DeviceType::CPU);
    device.commit();
    {
        const char* message = nullptr;
        const oidn::Error error = device.getError(message);
        if (error != oidn::Error::None)
        {
            PrintError("Could not initialize OIDN CPU device: %s", message ? message : "unknown error");
            return EXIT_FAILURE;
        }
    }

    std::map<int, std::vector<float>> replacements;

    PlanePixels beauty;
    if (!loadPlaneByName(multipart, multipart.beauty_name, beauty, "beauty"))
        return EXIT_FAILURE;
    PrintInfo("Denoising beauty subimage '%s'", beauty.subimage.name.c_str());
    if (!denoisePlane(device, beauty, albedo_ptr, normal_ptr))
        return EXIT_FAILURE;
    replacements[beauty.subimage.index] = std::move(beauty.pixels);

    for (const auto& aov : multipart.aov_names)
    {
        PlanePixels target;
        if (!loadPlaneByName(multipart, aov.second, target, "AOV"))
            return EXIT_FAILURE;

        PrintInfo("Denoising AOV subimage '%s'", target.subimage.name.c_str());
        if (!denoisePlane(device, target, albedo_ptr, normal_ptr))
            return EXIT_FAILURE;
        replacements[target.subimage.index] = std::move(target.pixels);
    }

    std::remove(multipart.output_filename.c_str());
    if (!writeMultipartOutput(multipart, multipart.output_filename, replacements))
        return EXIT_FAILURE;

    PrintInfo("Written out: %s", multipart.output_filename.c_str());
    PrintInfo("Done!");
    return EXIT_SUCCESS;
}
